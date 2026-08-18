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
 * Output (per race): data/<series>/fanduel/odds.json — current odds per tier,
 * normalized to implied win probability (raw) and a no-vig probability (raw
 * scaled to the market's number-of-winners), keyed so the page can match
 * drivers to Kalshi by name. For the full (Cup) series we also write
 * manufacturers.json and teams.json.
 *
 * The Kalshi scraper auto-discovers every open race into data/series.json; here
 * we load the page once (it carries every race's markets) and, for each series,
 * pick the FanDuel race whose name matches that series' Kalshi race — so the two
 * sides always describe the same race with no manual configuration.
 */

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const MOTORSPORT_URL = "https://nj.sportsbook.fanduel.com/motorsport";

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

// FanDuel finish-market labels -> our tier key (matches Kalshi's tier keys) and
// the number of drivers that "win" the market. FanDuel names these markets in
// one of two orders depending on the series module: "<race> - <label>" (F1,
// e.g. "Hungarian GP - Top 3 Finish") or "<label> - <race>" (NASCAR, e.g.
// "Top 3 Finish - Window World 450"); matchTier() handles both. The outright
// winner market is "Outright Betting" on some cards and "Race Winner" on others.
// FanDuel's Top-N markets report numberOfWinners=1 in their metadata (they're
// modeled as independent props), so we can't trust that field: the sum of
// P(finish top N) across the field is N, and that's what the no-vig
// normalization must target.
const TIER_SUFFIXES = [
  { key: "winner", labels: ["Outright Betting", "Race Winner"], winners: 1 },
  { key: "top3", labels: ["Top 3 Finish"], winners: 3 },
  { key: "top5", labels: ["Top 5 Finish"], winners: 5 },
  { key: "top10", labels: ["Top 10 Finish"], winners: 10 },
];
const TIER_WINNERS = Object.fromEntries(TIER_SUFFIXES.map((t) => [t.key, t.winners]));

// Escape a plain string for safe embedding in a RegExp.
const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

// If a market name is a single-race finish market for one of our tiers, return
// { key, race } with the race name taken from whichever side of the " - "
// separator it sits on; otherwise null. Season-long futures ("Cup Series 2026
// Outright Winner") and prop markets don't carry these exact labels and are
// naturally excluded.
function matchTier(name) {
  const n = (name || "").trim();
  for (const { key, labels } of TIER_SUFFIXES) {
    for (const label of labels) {
      const L = escapeRe(label);
      let m = n.match(new RegExp(`^(.+?) - ${L}$`, "i")); // "<race> - <label>"
      if (m) return { key, race: m[1].trim() };
      m = n.match(new RegExp(`^${L} - (.+)$`, "i")); // "<label> - <race>"
      if (m) return { key, race: m[1].trim() };
    }
  }
  return null;
}

const norm = (s) => (s || "").toLowerCase().replace(/[^a-z0-9]/g, "");

// American odds -> implied probability (0..1). Handles + and - integers.
function impliedProb(american) {
  if (typeof american !== "number" || american === 0) return null;
  return american > 0 ? 100 / (american + 100) : -american / (-american + 100);
}

// Read the auto-discovered races. Each series' Kalshi race name comes from its
// own data/<key>/index.json (written by scraper.py).
function readSeries() {
  let list = [];
  try {
    list = (JSON.parse(fs.readFileSync(path.join("data", "series.json"), "utf8")).series) || [];
  } catch {
    return [];
  }
  return list.map((s) => {
    let raceTitle = s.race_title || "";
    try {
      raceTitle = JSON.parse(fs.readFileSync(path.join("data", s.key, "index.json"), "utf8")).race_title || raceTitle;
    } catch { /* keep series.json value */ }
    return { key: s.key, label: s.label, race_title: raceTitle, full: !!s.full };
  });
}

// Pick the FanDuel race whose normalized name lines up with the Kalshi race
// (prefix match in either direction), or null if none match this race.
function pickRace(byRace, kalshiRace) {
  const kn = norm(kalshiRace);
  if (!kn) return null;
  return Object.keys(byRace).find((r) => {
    const rn = norm(r);
    return rn && (kn.startsWith(rn) || rn.startsWith(kn));
  }) || null;
}

async function main() {
  const seriesList = readSeries();
  console.log("Series to match:", seriesList.map((s) => `${s.key}:${s.race_title}`).join(", ") || "(none)");
  // The Kalshi scraper writes data/series.json; on a cold start the two
  // workflows can race, so just no-op until it exists (the next run picks up).
  if (!seriesList.length) { console.log("No data/series.json yet; nothing to scrape."); return; }

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
  const seenUrls = new Set();
  page.on("response", async (r) => {
    const u = r.url();
    if (/content-managed-page|getMarketPrices|coupon|competition|nascar/i.test(u)) seenUrls.add(u);
    if (!/content-managed-page|getMarketPrices/.test(u)) return;
    try {
      const att = (await r.json()).attachments || {};
      Object.assign(events, att.events || {});
      Object.assign(markets, att.markets || {});
    } catch {
      /* non-JSON or already-consumed body; ignore */
    }
  });

  // The /motorsport landing (content-managed-page?page=SPORT&eventTypeId=8)
  // lists every motorsport EVENT but only prices the featured competition's
  // markets (e.g. an F1 Grand Prix on an F1 weekend). NASCAR races are listed
  // as events but their markets aren't fetched there, so after the landing load
  // we pull each NASCAR competition's/event's own content-managed-page from the
  // app's sbapi — called in-page via fetch() so the page's cookies and the _ak
  // client key apply — and merge the priced markets in.
  await page.goto(MOTORSPORT_URL, { waitUntil: "networkidle", timeout: 90000 }).catch(() => {});
  await page.waitForTimeout(7000);

  const cmpUrl = [...seenUrls].find((u) => /content-managed-page/.test(u)) || "";
  const ak = (cmpUrl.match(/[?&]_ak=([^&]+)/) || [])[1] || "";
  const apiBase = cmpUrl.split("?")[0] ||
    "https://api.sportsbook.fanduel.com/sbapi/content-managed-page";
  const nascarEvents = Object.values(events).filter((e) => /nascar/i.test(e.name || ""));
  const comps = [...new Set(nascarEvents.map((e) => e.competitionId).filter(Boolean))];
  const queries = [
    ...comps.map((cid) => `page=COMPETITION&competitionId=${cid}`),
    ...nascarEvents.map((e) => e.eventId).filter(Boolean).map((eid) => `page=EVENT&eventId=${eid}`),
  ];
  console.log(`nascar comps=[${comps.join(",")}] ak=${ak ? "yes" : "no"} queries=${queries.length}`);
  // Use Playwright's APIRequestContext (page.request) rather than an in-page
  // fetch(): it reuses the browser context's cookies (incl. the PerimeterX
  // tokens set during the page load) but is NOT subject to the page's CORS
  // sandbox, so the cross-origin api.sportsbook.fanduel.com call succeeds.
  for (const qs of queries) {
    const url = `${apiBase}?${qs}&_ak=${ak}&timezone=America/New_York`;
    const before = Object.keys(markets).length;
    try {
      const resp = await page.request.get(url, { headers: { accept: "application/json" } });
      if (!resp.ok()) { console.log(`  ${qs} -> HTTP ${resp.status()}`); continue; }
      const att = (await resp.json()).attachments || {};
      Object.assign(events, att.events || {});
      Object.assign(markets, att.markets || {});
      console.log(`  ${qs} -> +${Object.keys(markets).length - before} markets`);
    } catch (e) {
      console.log(`  ${qs} -> err ${String(e.message || e).split("\n")[0]}`);
    }
  }
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
    const hit = matchTier(m.marketName || "");
    if (!hit) continue;
    (byRace[hit.race] = byRace[hit.race] || {})[hit.key] = m;
  }
  const raceNames = Object.keys(byRace);
  console.log("FanDuel race markets found for:", raceNames);
  if (!raceNames.length) throw new Error("No single-race outright markets found on FanDuel.");

  for (const series of seriesList) emitSeries(series, byRace, markets);
}

// Write one series' FanDuel odds (and, for the full series, manufacturer/team
// markets) under data/<series>/fanduel/.
function emitSeries(series, byRace, markets) {
  const kalshiRace = series.race_title;
  const chosen = pickRace(byRace, kalshiRace);
  const outDir = path.join("data", series.key, "fanduel");
  if (!chosen) {
    console.log(`[${series.key}] no FanDuel race matches "${kalshiRace}"; skipping.`);
    return;
  }
  console.log(`[${series.key}] "${kalshiRace}" -> FanDuel "${chosen}"`);

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
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(path.join(outDir, "odds.json"), JSON.stringify(out, null, 2) + "\n");
  console.log(`  wrote ${path.join(outDir, "odds.json")}`);

  // Manufacturer/Team markets are Cup-only (the support series don't have them).
  if (series.full) {
    scrapeManufacturers(markets, chosen, kalshiRace, outDir);
    scrapeTeams(markets, chosen, kalshiRace, outDir);
  }
}

// FanDuel's winning-team market: runners are race teams. Detected by runner set
// (rather than market name) so it survives renames, and gated to the chosen race
// so the season-long owner championship is excluded. Output feeds the Top Team
// tab's "which team wins" comparison.
function scrapeTeams(markets, chosenRace, kalshiRace, outDir) {
  const teamFile = path.join(outDir, "teams.json");
  const raceNorm = norm(chosenRace);
  const runnerAmerican = (r) =>
    r.winRunnerOdds && r.winRunnerOdds.americanDisplayOdds
      ? r.winRunnerOdds.americanDisplayOdds.americanOdds
      : null;

  const raceMarkets = Object.values(markets).filter(
    (m) => raceNorm && norm(m.marketName || "").includes(raceNorm)
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
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(teamFile, JSON.stringify(out, null, 2) + "\n");
  console.log(`  winning-team market: ${teamMkt.marketName} (${entries.length} teams) -> ${teamFile}`);
}

// FanDuel's manufacturer props: a "winning manufacturer" market (runners are the
// makes) and, when offered, per-make "highest finishing / top [Make]" driver
// markets. We detect the winner market by its runner set (rather than guessing
// the exact market name) so it keeps working if FanDuel renames it, and we
// exclude the season-long championship by requiring the market name to reference
// the chosen race. Output feeds the dashboard's Top Manufacturer tab.
function scrapeManufacturers(markets, chosenRace, kalshiRace, outDir) {
  const mfrFile = path.join(outDir, "manufacturers.json");
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
  const raceMarkets = all.filter((m) => raceNorm && norm(m.marketName || "").includes(raceNorm));
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
    fs.mkdirSync(outDir, { recursive: true });
    fs.writeFileSync(mfrFile, JSON.stringify(result, null, 2) + "\n");
    console.log("wrote", mfrFile);
  } else {
    console.log("no manufacturer markets captured; leaving", mfrFile, "untouched.");
  }
}

main().catch((e) => {
  console.error("FATAL:", e.message);
  process.exit(1);
});

// manual re-scrape trigger 2026-07-18T14:21:40Z (MCP dispatch unavailable)
