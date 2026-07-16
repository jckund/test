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

// Number of players that "win" each tier (for the no-vig normalization).
const TIER_WINNERS = { winner: 1, top5: 5, top10: 10, top20: 20 };

// Derivative/novelty golf markets that must NOT be mistaken for a real tier:
// "Winner w/o McIlroy / Scheffler", "Two/Three/Four Chances to Win", hole and
// round match-ups, groups, 3-balls, first-round leader, make/miss cut, etc. A
// slash in the name signals a multi-name novelty ("A / B / C", "w/o X / Y").
const NOVELTY = /(w\/o|without|chances to win|\bholes?\b|round\s*[1-4]|\br[1-4]\b|group|\bmatch\b|[0-9]\s*-?\s*ball|first round leader|\bfrl\b|make (the )?cut|miss (the )?cut|nationality|top \w+ (golfer|player|nationality)|\/)/i;

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
// { key, winners, incl } or null. Novelty/derivative markets are rejected, and
// the specific top-N tiers are tested before the generic outright winner.
// `incl` flags the "(Incl. Ties)" variant, which matches Kalshi's semantics
// (a top-N finish counts ties), so emit() can prefer it.
function matchTier(name) {
  const n = (name || "").toLowerCase().trim();
  if (!n || NOVELTY.test(n)) return null;
  const incl = /incl/.test(n) && /ties/.test(n);
  if (/top\s*-?\s*20/.test(n)) return { key: "top20", winners: 20, incl };
  if (/top\s*-?\s*10/.test(n)) return { key: "top10", winners: 10, incl };
  if (/top\s*-?\s*5/.test(n)) return { key: "top5", winners: 5, incl };
  // Outright winner: only a plain "Winner" / "Outright (Winner)" / "To Win"
  // market (novelties already filtered out above).
  if (/^(winner|outright winner|outright|tournament winner|to win outright)\b/.test(n) || n === "to win")
    return { key: "winner", winners: 1, incl: false };
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

  // The golf landing page carries the Top-N finish markets but not the outright
  // "Winner" market — that lives on the tournament's own page. Follow the golf
  // links on the page (the response interceptor keeps accumulating markets) so
  // the outright gets captured too. Best-effort: any failure leaves us with the
  // landing-page markets we already have.
  try {
    const origin = new URL(GOLF_URL).origin;
    const links = await page.$$eval('a[href*="/golf/"]', (as) =>
      as.map((a) => ({ href: a.getAttribute("href") || "", text: (a.textContent || "").trim() })));
    const seen = new Set();
    const targets = [];
    for (const l of links) {
      const hay = (l.href + " " + l.text).toLowerCase();
      // Follow links that point at The Open / an outright-winner view.
      if (!/open|championship|winner|outright/.test(hay)) continue;
      const abs = l.href.startsWith("http") ? l.href : origin + l.href;
      if (seen.has(abs)) continue;
      seen.add(abs);
      targets.push(abs);
    }
    console.log(`Following ${targets.length} golf link(s) for the outright:`, targets.slice(0, 8));
    for (const url of targets.slice(0, 8)) {
      await page.goto(url, { waitUntil: "networkidle", timeout: 60000 }).catch(() => {});
      await page.waitForTimeout(4000);
    }
  } catch (e) {
    console.log("outright link-follow failed (keeping landing markets):", e.message);
  }

  await browser.close();

  const nMarkets = Object.keys(markets).length;
  console.log(`captured events=${Object.keys(events).length} markets=${nMarkets}`);
  if (!nMarkets) throw new Error("No FanDuel markets captured (page structure changed or blocked).");

  // Log the captured events (id + name + any URL/slug) so the outright-winner
  // page can be located when it isn't on the golf landing view.
  console.log("Captured events:");
  for (const [id, e] of Object.entries(events)) {
    const nm = e.name || e.eventName || "";
    const slug = e.url || e.link || e.slug || "";
    console.log(`  ${id}: "${nm}"${slug ? "  <" + slug + ">" : ""}`);
  }

  const evName = (m) => (events[m.eventId] && (events[m.eventId].name || events[m.eventId].eventName)) || "";

  // Candidate finish markets, each tagged with the event name it belongs to (for
  // tournament attribution). Log them all so labels can be refined from CI logs.
  const candidates = [];
  for (const m of Object.values(markets)) {
    const hit = matchTier(m.marketName || "");
    if (!hit) continue;
    candidates.push({ m, key: hit.key, winners: hit.winners, incl: hit.incl, evName: evName(m) });
  }
  console.log("Candidate finish markets:");
  for (const c of candidates) console.log(`  [${c.key}${c.incl ? "+ties" : ""}] "${c.m.marketName}"  (event: "${c.evName}", runners: ${(c.m.runners || []).length})`);
  if (!candidates.length) throw new Error("No golf finish markets matched (see captured market names above).");

  for (const t of tournaments) emitTournament(t, candidates);
}

// Write one tournament's FanDuel odds under data/<key>/fanduel/odds.json.
function emitTournament(t, candidates) {
  const outDir = path.join("data", t.key, "fanduel");
  // Attribute each candidate to this tournament by title-token overlap against
  // the market name or its event name. Keep the best-scoring market per tier.
  const best = {}; // tierKey -> { m, winners, score, incl }
  for (const c of candidates) {
    const score = Math.max(titleScore(t.race_title, c.m.marketName), titleScore(t.race_title, c.evName));
    if (score === 0) continue; // doesn't reference this tournament
    const runners = (c.m.runners || []).length;
    const prev = best[c.key];
    // Rank candidates for a tier by, in order: strongest tournament-title match;
    // then the "(Incl. Ties)" variant (matches Kalshi's top-N-with-ties); then
    // the most runners (the real field market, not a small special).
    const better = !prev
      || score > prev.score
      || (score === prev.score && !!c.incl > !!prev.incl)
      || (score === prev.score && !!c.incl === !!prev.incl && runners > (prev.m.runners || []).length);
    if (better) best[c.key] = { m: c.m, winners: c.winners, score, incl: c.incl };
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
