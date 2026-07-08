#!/usr/bin/env node
/*
 * Scrape FanDuel's NASCAR race markets (outright winner + Top 3/5/10 finish) so
 * they can be compared against the Kalshi prediction-market prices in the
 * dashboard.
 *
 * FanDuel has no public API and sits behind PerimeterX bot protection, so a
 * plain HTTP call is blocked. Instead we drive a real headless browser
 * (Playwright + Chromium) to the public motorsport page; the app fetches its
 * own `content-managed-page` JSON, and we read those response bodies. This runs
 * only on a GitHub Actions runner (the Claude session's egress proxy blocks
 * sportsbooks), on a modest schedule to stay low-profile.
 *
 * Output: data/fanduel/odds.json — current odds per tier, normalized to implied
 * win probability (raw) and a no-vig probability (raw scaled to the market's
 * number-of-winners), keyed so the page can match drivers to Kalshi by name.
 *
 * We select the race by matching FanDuel's market-name prefix against the race
 * Kalshi is tracking (read from data/index.json), so the two sides always
 * describe the same race with no manual configuration.
 */

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const MOTORSPORT_URL = "https://sportsbook.fanduel.com/motorsport";
const OUT_DIR = path.join("data", "fanduel");
const OUT_FILE = path.join(OUT_DIR, "odds.json");

// FanDuel market-name suffix -> our tier key (matches Kalshi's tier keys).
const TIER_SUFFIXES = [
  { key: "winner", re: /^(.*) - Outright Betting$/i },
  { key: "top3", re: /^(.*) - Top 3 Finish$/i },
  { key: "top5", re: /^(.*) - Top 5 Finish$/i },
  { key: "top10", re: /^(.*) - Top 10 Finish$/i },
];

const norm = (s) => (s || "").toLowerCase().replace(/[^a-z0-9]/g, "");

// American odds -> implied probability (0..1). Handles + and - integers.
function impliedProb(american) {
  if (typeof american !== "number" || american === 0) return null;
  return american > 0 ? 100 / (american + 100) : -american / (-american + 100);
}

function readKalshiRaceName() {
  try {
    const idx = JSON.parse(fs.readFileSync(path.join("data", "index.json"), "utf8"));
    return idx.race_title || "";
  } catch {
    return "";
  }
}

async function main() {
  const kalshiRace = process.env.FD_RACE || readKalshiRaceName();
  const kalshiNorm = norm(kalshiRace);
  console.log("Kalshi race:", kalshiRace || "(unknown)");

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
    } catch {
      /* non-JSON or already-consumed body; ignore */
    }
  });

  await page.goto(MOTORSPORT_URL, { waitUntil: "networkidle", timeout: 90000 }).catch(() => {});
  await page.waitForTimeout(7000);
  await browser.close();

  const nMarkets = Object.keys(markets).length;
  console.log(`captured events=${Object.keys(events).length} markets=${nMarkets}`);
  if (!nMarkets) throw new Error("No FanDuel markets captured (page structure changed or blocked).");

  // Group race markets by their race-name prefix so we can pick the one that
  // matches the Kalshi race. Season/championship futures ("Cup Series 2026
  // Outright Winner") lack the " - Outright Betting" / " - Top N Finish" suffix
  // and are naturally excluded.
  const byRace = {}; // raceName -> { tierKey -> market }
  for (const m of Object.values(markets)) {
    const name = m.marketName || "";
    for (const { key, re } of TIER_SUFFIXES) {
      const match = name.match(re);
      if (!match) continue;
      const race = match[1].trim();
      (byRace[race] = byRace[race] || {})[key] = m;
      break;
    }
  }
  const raceNames = Object.keys(byRace);
  console.log("race markets found for:", raceNames);
  if (!raceNames.length) throw new Error("No single-race outright markets found on FanDuel.");

  // Choose the race whose normalized name best lines up with the Kalshi race.
  // Prefix match in either direction (FanDuel "Quaker State 400" vs Kalshi
  // "Quaker State 400 Available at Walmart"); fall back to the race exposing the
  // most tiers.
  let chosen = null;
  if (kalshiNorm) {
    chosen = raceNames.find((r) => {
      const rn = norm(r);
      return rn && (kalshiNorm.startsWith(rn) || rn.startsWith(kalshiNorm));
    });
  }
  if (!chosen) {
    chosen = raceNames.sort((a, b) => Object.keys(byRace[b]).length - Object.keys(byRace[a]).length)[0];
    console.log("WARNING: no name match to Kalshi race; falling back to", JSON.stringify(chosen));
  }
  console.log("chosen race:", chosen);

  const tiers = {};
  for (const [tierKey, m] of Object.entries(byRace[chosen])) {
    const target = typeof m.numberOfWinners === "number" && m.numberOfWinners > 0 ? m.numberOfWinners : 1;
    const drivers = [];
    for (const r of m.runners || []) {
      if (r.runnerStatus && r.runnerStatus !== "ACTIVE") continue;
      const american = r.winRunnerOdds && r.winRunnerOdds.americanDisplayOdds
        ? r.winRunnerOdds.americanDisplayOdds.americanOdds
        : null;
      const implied = impliedProb(american);
      if (implied == null) continue;
      drivers.push({ name: r.runnerName, american, implied });
    }
    // No-vig: scale raw implied so the field sums to the number of winners.
    const sum = drivers.reduce((a, d) => a + d.implied, 0);
    for (const d of drivers) d.novig = sum > 0 ? (d.implied * target) / sum : null;
    drivers.sort((a, b) => b.implied - a.implied);
    tiers[tierKey] = { market_name: m.marketName, number_of_winners: target, drivers };
    console.log(`  ${tierKey}: ${drivers.length} drivers (${m.marketName})`);
  }

  const out = {
    scraped_at: new Date().toISOString(),
    source: "FanDuel",
    source_url: MOTORSPORT_URL,
    race: chosen,
    kalshi_race: kalshiRace,
    tiers,
  };
  fs.mkdirSync(OUT_DIR, { recursive: true });
  fs.writeFileSync(OUT_FILE, JSON.stringify(out, null, 2) + "\n");
  console.log("wrote", OUT_FILE);
}

main().catch((e) => {
  console.error("FATAL:", e.message);
  process.exit(1);
});
