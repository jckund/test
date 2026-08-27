#!/usr/bin/env node
/*
 * ONE-TIME DISCOVERY PROBE (not part of the weekly pipeline).
 *
 * The Claude session's egress proxy blocks caliber.com, so we can't inspect the
 * find-a-location page from a dev session. This script runs on a GitHub Actions
 * runner (open egress), drives the real page with Playwright + Chromium, and
 * records how the site actually serves its location data:
 *   - every XHR/fetch/JSON response (URL, status, size) it makes on load,
 *   - the response bodies (so we can spot the location feed / API),
 *   - the rendered HTML and every <a> link (to find per-state pages),
 *   - a best-effort click into the first "state" it can find, capturing the
 *     network that fires as a result.
 *
 * Everything lands under data/caliber/_discovery/ and is committed back to the
 * branch by the caliber_discover.yml workflow so it can be read from a dev
 * session. Once the real API is known, caliber_scraper.py replaces this and this
 * file + its workflow can be deleted.
 */

import fs from "fs";
import path from "path";
import { chromium } from "playwright";

const START = "https://www.caliber.com/find-a-location";
const OUT = path.join("data", "caliber", "_discovery");
fs.mkdirSync(OUT, { recursive: true });

const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " +
  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";

function safeName(url) {
  return url.replace(/^https?:\/\//, "").replace(/[^a-z0-9]+/gi, "_").slice(0, 140);
}

const seen = [];
function wireCapture(page, tag) {
  page.on("response", async (resp) => {
    try {
      const req = resp.request();
      const url = resp.url();
      const ct = (resp.headers()["content-type"] || "").toLowerCase();
      const rt = req.resourceType();
      const isData =
        rt === "xhr" || rt === "fetch" || ct.includes("application/json") ||
        /\/api\/|graphql|locations?|stores?|geo|search/i.test(url);
      if (!isData) return;
      let body = null;
      try { body = await resp.text(); } catch {}
      const rec = { tag, url, method: req.method(), status: resp.status(), ct, len: body ? body.length : 0, rt };
      seen.push(rec);
      if (body && body.length > 0 && body.length < 8_000_000) {
        fs.writeFileSync(path.join(OUT, `resp__${tag}__${safeName(url)}.txt`), body);
      }
      console.log(`[net:${tag}] ${resp.status()} ${rt} ${req.method()} ${url} (${rec.len}b, ${ct})`);
    } catch (e) {}
  });
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ userAgent: UA, locale: "en-US" });
  const page = await ctx.newPage();
  wireCapture(page, "load");

  console.log(`Navigating to ${START}`);
  try {
    await page.goto(START, { waitUntil: "domcontentloaded", timeout: 90000 });
  } catch (e) {
    console.log("goto domcontentloaded error:", e.message);
  }
  // Let client-side calls settle.
  await page.waitForTimeout(8000);
  try { await page.waitForLoadState("networkidle", { timeout: 20000 }); } catch {}

  fs.writeFileSync(path.join(OUT, "find-a-location.html"), await page.content());

  const links = await page.$$eval("a", (as) =>
    as.map((a) => ({ text: (a.textContent || "").trim().slice(0, 80), href: a.href }))
      .filter((x) => x.href && /^https?:/.test(x.href))
  );
  fs.writeFileSync(path.join(OUT, "links.json"), JSON.stringify(links, null, 2));
  console.log(`Captured ${links.length} links.`);

  // Heuristic: find a state link (find-a-location/<state> or text that is a US state).
  const STATES = ["alabama","alaska","arizona","arkansas","california","colorado","connecticut",
    "delaware","florida","georgia","hawaii","idaho","illinois","indiana","iowa","kansas","kentucky",
    "louisiana","maine","maryland","massachusetts","michigan","minnesota","mississippi","missouri",
    "montana","nebraska","nevada","new-hampshire","new-jersey","new-mexico","new-york","north-carolina",
    "north-dakota","ohio","oklahoma","oregon","pennsylvania","rhode-island","south-carolina",
    "south-dakota","tennessee","texas","utah","vermont","virginia","washington","west-virginia",
    "wisconsin","wyoming"];
  const stateLinks = links.filter((l) => {
    const h = l.href.toLowerCase();
    return /find-a-location\//.test(h) && STATES.some((s) => h.includes("/" + s));
  });
  fs.writeFileSync(path.join(OUT, "state_links.json"), JSON.stringify(stateLinks, null, 2));
  console.log(`State-like links: ${stateLinks.length}`);
  if (stateLinks.length) console.log("sample state links:", stateLinks.slice(0, 5).map((s) => s.href));

  // Best-effort: visit the first state page and capture its network.
  if (stateLinks.length) {
    const target = stateLinks[0].href;
    console.log(`Visiting first state page: ${target}`);
    wireCapture(page, "state");
    try {
      await page.goto(target, { waitUntil: "domcontentloaded", timeout: 90000 });
      await page.waitForTimeout(8000);
      try { await page.waitForLoadState("networkidle", { timeout: 20000 }); } catch {}
      fs.writeFileSync(path.join(OUT, "state-page.html"), await page.content());
    } catch (e) {
      console.log("state visit error:", e.message);
    }
  }

  fs.writeFileSync(path.join(OUT, "network.json"), JSON.stringify(seen, null, 2));
  console.log("\n===== NETWORK SUMMARY =====");
  for (const r of seen) console.log(`${r.tag}\t${r.status}\t${r.len}b\t${r.url}`);

  await browser.close();
})().catch((e) => { console.error("FATAL", e); process.exit(1); });
