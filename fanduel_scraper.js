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
const MFR_FILE = path.join(OUT_DIR, "manufacturers.json");
const TEAM_FILE = path.join(OUT_DIR, "teams.json");

// Canonical manufacturer names we recognize as runners in a "winning
// manufacturer" market (and as keywords in per-make driver markets).
const MAKES = ["Chevrolet", "Ford", "Toyota"];
const MAKE_NORM = MAKES.map((m) => m.toLowerCase());

// Map a book's team-name string to our canonical team key by keyword (keep in
// sync with teamCanon() in index.html).
const TEAM_RULES = [
  ["penske", "Team Penske"], ["hendrick", "Hendrick Motorsports"], ["gibbs", "Joe Gibbs Racing"],
  ["23xi", "23XI Racing"], ["rfk", "RFK Racing"], ["roush", "RFK Racing"], ["spire", "Spire Motorsports"],
  ["trackhouse", "Trackhouse Racing"], ["front row", "Front Row Motorsports"], ["hyak", "Hyak Motorsports"],
  ["legacy", "Legacy Motor Club"], ["childress", "Richard Childress Racing"], ["kaulig", "Kaulig Racing"],
  ["wood brothers", "Wood Brothers Racing"], ["haas", "Haas Factory Team"], ["hass", "Haas Factory Team"],
  ["rick ware", "Rick Ware Racing"], ["garage 66", "Garage 66"], ["garage66", "Garage 66"],
  ["live fast", "Live Fast Motorsports"],
];
function teamCanon(name) {
  const n = (name || "").toLowerCase();
  for (const [kw, canon] of TEAM_RULES) if (n.includes(kw)) return canon;
  return null;
}

// FanDuel market-name suffix -> our tier key (matches Kalshi's tier keys) and
// the number of drivers that "win" the market. FanDuel's Top-N markets report
// numberOfWinners=1 in their metadata (they're modeled as independent props),
// so we can't trust that field: the sum of P(finish top N) across the field is
// N, and that's what the no-vig normalization must target.
const TIER_SUFFIXES = [
  { key: "winner", re: /^(.*) - Outright Betting$/i, winners: 1 },
  { key: "top3", re: /^(.*) - Top 3 Finish$/i, winners: 3 },
  { key: "top5", re: /^(.*) - Top 5 Finish$/i, winners: 5 },
  { key: "top10", re: /^(.*) - Top 10 Finish$/i, winners: 10 },
];
const TIER_WINNERS = Object.fromEntries(TIER_SUFFIXES.map((t) => [t.key, t.winners]));

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
    const target = TIER_WINNERS[tierKey] || 1;
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

  scrapeManufacturers(markets, chosen, kalshiRace);
  scrapeTeams(markets, chosen, kalshiRace);
}

// FanDuel's winning-team market: runners are race teams. Detected by runner set
// (rather than market name) so it survives renames, and gated to the chosen race
// so the season-long owner championship is excluded. Output feeds the Top Team
// tab's "which team wins" comparison.
function scrapeTeams(markets, chosenRace, kalshiRace) {
  const raceNorm = norm(chosenRace);
  const runnerAmerican = (r) =>
    r.winRunnerOdds && r.winRunnerOdds.americanDisplayOdds
      ? r.winRunnerOdds.americanDisplayOdds.americanOdds
      : null;

  const raceMarkets = Object.values(markets).filter(
    (m) => raceNorm && norm(m.marketName || "").startsWith(raceNorm)
  );
  const teamMkt = raceMarkets.find((m) => {
    const rs = (m.runners || []).map((r) => teamCanon(r.runnerName)).filter(Boolean);
    return rs.length >= 3 && rs.length >= (m.runners || []).length - 1;
  });

  if (!teamMkt) {
    console.log("  no winning-team market found for this race.");
    return;
  }
  const entries = [];
  for (const r of teamMkt.runners || []) {
    if (r.runnerStatus && r.runnerStatus !== "ACTIVE") continue;
    const team = teamCanon(r.runnerName);
    const american = runnerAmerican(r);
    const implied = impliedProb(american);
    if (!team || implied == null) continue;
    entries.push({ team, american, implied });
  }
  const sum = entries.reduce((a, e) => a + e.implied, 0);
  const winner = {};
  for (const e of entries) {
    winner[e.team] = { american: e.american, implied: e.implied, novig: sum > 0 ? e.implied / sum : null };
  }
  const out = {
    scraped_at: new Date().toISOString(),
    source: "FanDuel",
    source_url: MOTORSPORT_URL,
    race: chosenRace,
    kalshi_race: kalshiRace,
    winner,
  };
  fs.writeFileSync(TEAM_FILE, JSON.stringify(out, null, 2) + "\n");
  console.log(`  winning-team market: ${teamMkt.marketName} (${entries.length} teams) -> ${TEAM_FILE}`);
}

// FanDuel's manufacturer props: a "winning manufacturer" market (runners are the
// makes) and, when offered, per-make "highest finishing / top [Make]" driver
// markets. We detect the winner market by its runner set (rather than guessing
// the exact market name) so it keeps working if FanDuel renames it, and we
// exclude the season-long championship by requiring the market name to reference
// the chosen race. Output feeds the dashboard's Top Manufacturer tab.
function scrapeManufacturers(markets, chosenRace, kalshiRace) {
  const raceNorm = norm(chosenRace);
  const runnerAmerican = (r) =>
    r.winRunnerOdds && r.winRunnerOdds.americanDisplayOdds
      ? r.winRunnerOdds.americanDisplayOdds.americanOdds
      : null;
  const canonMake = (name) => {
    const n = (name || "").toLowerCase();
    const i = MAKE_NORM.findIndex((m) => n.includes(m));
    return i >= 0 ? MAKES[i] : null;
  };

  const all = Object.values(markets);
  // Log every market whose name references this race, to reveal manufacturer
  // market naming for future refinement.
  const raceMarkets = all.filter((m) => raceNorm && norm(m.marketName || "").startsWith(raceNorm));
  console.log("markets for chosen race:", raceMarkets.map((m) => m.marketName));

  // Winning-manufacturer market: runners are (mostly) makes, and the market name
  // references the chosen race so we don't grab the season championship.
  const winnerMkt = raceMarkets.find((m) => {
    const rs = (m.runners || []).map((r) => canonMake(r.runnerName)).filter(Boolean);
    return rs.length >= 2 && rs.length >= (m.runners || []).length - 1;
  });

  const result = {
    scraped_at: new Date().toISOString(),
    source: "FanDuel",
    source_url: MOTORSPORT_URL,
    race: chosenRace,
    kalshi_race: kalshiRace,
    winner: {},
    makes: {},
  };

  if (winnerMkt) {
    const entries = [];
    for (const r of winnerMkt.runners || []) {
      if (r.runnerStatus && r.runnerStatus !== "ACTIVE") continue;
      const make = canonMake(r.runnerName);
      const american = runnerAmerican(r);
      const implied = impliedProb(american);
      if (!make || implied == null) continue;
      entries.push({ make, american, implied });
    }
    const sum = entries.reduce((a, e) => a + e.implied, 0);
    for (const e of entries) {
      result.winner[e.make] = {
        american: e.american,
        implied: e.implied,
        novig: sum > 0 ? e.implied / sum : null,
      };
    }
    console.log(`  winning-manufacturer market: ${winnerMkt.marketName} (${entries.length} makes)`);
  } else {
    console.log("  no winning-manufacturer market found for this race.");
  }

  // Per-make driver markets (e.g. "... - Top Chevrolet Driver"), if offered.
  // Detect by a make keyword in the market name that is NOT the winner market
  // and whose runners are drivers (not makes).
  for (const m of raceMarkets) {
    if (m === winnerMkt) continue;
    const make = canonMake(m.marketName);
    if (!make) continue;
    const runnersAreMakes = (m.runners || []).some((r) => canonMake(r.runnerName));
    if (runnersAreMakes) continue;
    const drivers = [];
    for (const r of m.runners || []) {
      if (r.runnerStatus && r.runnerStatus !== "ACTIVE") continue;
      const american = runnerAmerican(r);
      const implied = impliedProb(american);
      if (implied == null) continue;
      drivers.push({ name: r.runnerName, american, implied });
    }
    if (!drivers.length) continue;
    const sum = drivers.reduce((a, d) => a + d.implied, 0);
    for (const d of drivers) d.novig = sum > 0 ? d.implied / sum : null;
    drivers.sort((a, b) => b.implied - a.implied);
    result.makes[make] = { market_name: m.marketName, drivers };
    console.log(`  top-${make} market: ${m.marketName} (${drivers.length} drivers)`);
  }

  if (Object.keys(result.winner).length || Object.keys(result.makes).length) {
    fs.writeFileSync(MFR_FILE, JSON.stringify(result, null, 2) + "\n");
    console.log("wrote", MFR_FILE);
  } else {
    console.log("no manufacturer markets captured; leaving", MFR_FILE, "untouched.");
  }
}

main().catch((e) => {
  console.error("FATAL:", e.message);
  process.exit(1);
});
