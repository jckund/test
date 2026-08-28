#!/usr/bin/env python3
"""Scrape every Gerber Collision & Glass location from gerbercollision.com.

The locator at https://www.gerbercollision.com/locations is server-rendered
HTML: an index page links to per-state pages (/locations/<state>-xx), and each
state page lists its centers (25 per page, paginated with ?n=2,3,...). Each
center block carries a stable slug, a numeric store id, name, address, phone and
lat/lng. Pulling every state's every page is the programmatic equivalent of
clicking into each state.

Runs on a GitHub Actions runner — gerbercollision.com is not reachable from a
Claude session (proxy), so run this in CI, never inline.

Output (mirrors the Caliber watcher's shape so the report/email code is shared):
  data/gerber/locations.json  -- {slug: {normalized center}}, sorted. Changes
                                 only on a real add/remove/edit.
  data/gerber/meta.json       -- {captured_at, count, states, source} heartbeat.
"""
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

BASE = "https://www.gerbercollision.com"
INDEX = f"{BASE}/locations"
PAGE_SIZE = 25
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

OUT_DIR = os.path.join("data", "gerber")
LOCATIONS_PATH = os.path.join(OUT_DIR, "locations.json")
META_PATH = os.path.join(OUT_DIR, "meta.json")

RESULT_RE = re.compile(r'<div class="row result" href="/locations/([^"]+)">(.*?)(?=<div class="row result"|<hr class="line"|</div>\s*</div>\s*<hr|\Z)', re.S)
# Simpler: split into blocks on the result marker and parse each chunk.
BLOCK_SPLIT = re.compile(r'<div class="row result" href="/locations/')


def _txt(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s or "")).strip()


def parse_state_html(html):
    """Return a list of normalized center dicts found on one state page."""
    out = []
    parts = BLOCK_SPLIT.split(html)[1:]  # drop preamble
    for chunk in parts:
        m = re.match(r'([^"]+)">', chunk)
        if not m:
            continue
        slug = m.group(1).strip()
        lat = re.search(r'data-lat="([^"]*)"', chunk)
        lng = re.search(r'data-lng="([^"]*)"', chunk)
        sid = re.search(r'data-id="([^"]*)"', chunk)
        name = re.search(r'<h2>.*?<a[^>]*>(.*?)</a>', chunk, re.S)
        addr = re.search(r'<address[^>]*>(.*?)</address>', chunk, re.S)
        # visible phone text (the tel: href on this site is malformed)
        phone = re.search(r'href="tel:[^"]*">\s*(.*?)\s*<', chunk, re.S)

        address = _txt(addr.group(1)) if addr else ""
        city = state = zipc = street = ""
        am = re.search(r"^(.*),\s*([^,]+),\s*([A-Z]{2})\s+(\d{5})(?:-\d{4})?$", address)
        if am:
            street, city, state, zipc = (am.group(1).strip(), am.group(2).strip(),
                                         am.group(3), am.group(4))

        def num(x):
            try:
                return float(x)
            except (TypeError, ValueError):
                return ""

        out.append({
            "identifier": slug,
            "storeId": (sid.group(1).strip() if sid else ""),
            "name": _txt(name.group(1)) if name else "",
            "address1": street,
            "city": city,
            "state": state,
            "zip": zipc,
            "address": address,
            "phone": _txt(phone.group(1)) if phone else "",
            "latitude": num(lat.group(1)) if lat else "",
            "longitude": num(lng.group(1)) if lng else "",
            "url": f"{BASE}/locations/{slug}",
        })
    return out


def _get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read().decode("utf-8", "replace")
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"failed to fetch {url}: {last}")


def state_slugs(index_html):
    """State page slugs are exactly the /locations/<x> links on the index."""
    return sorted(set(re.findall(r'href="/locations/([a-z-]+)"', index_html)))


def total_count(state_html):
    m = re.search(r"of\s*<strong>\s*([\d,]+)\s*</strong>\s*Locations", state_html)
    if not m:
        m = re.search(r"of\s*([\d,]+)\s*Locations", state_html)
    return int(m.group(1).replace(",", "")) if m else None


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    index = _get(INDEX)
    states = state_slugs(index)
    print(f"Found {len(states)} states")

    by_slug = {}
    for st in states:
        first = _get(f"{BASE}/locations/{st}")
        n = total_count(first)
        pages = 1 if not n else max(1, math.ceil(n / PAGE_SIZE))
        got = 0
        for c in parse_state_html(first):
            by_slug[c["identifier"]] = c
            got += 1
        for p in range(2, pages + 1):
            for c in parse_state_html(_get(f"{BASE}/locations/{st}?n={p}")):
                by_slug[c["identifier"]] = c
                got += 1
        print(f"  {st}: {got} rows (reported {n}), {pages} page(s)")

    if not by_slug:
        print("ERROR: zero centers parsed — refusing to overwrite snapshot.", file=sys.stderr)
        return 1

    locations = dict(sorted(by_slug.items()))
    with open(LOCATIONS_PATH, "w") as f:
        json.dump(locations, f, indent=2, sort_keys=True)
        f.write("\n")

    by_state = {}
    for c in locations.values():
        by_state[c["state"] or "??"] = by_state.get(c["state"] or "??", 0) + 1
    meta = {
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(locations),
        "states": len([s for s in by_state if s != "??"]),
        "source": INDEX,
    }
    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")
    print(f"Wrote {len(locations)} centers across {meta['states']} states -> {LOCATIONS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
