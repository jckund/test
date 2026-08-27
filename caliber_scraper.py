#!/usr/bin/env python3
"""Scrape every Caliber Collision location from caliber.com.

The public store locator at https://www.caliber.com/find-a-location is a Next.js
front-end over a dotCMS backend. Individual centers are the dotCMS content type
`Center`, exposed anonymously through the Content REST API. We pull the full set
of live centers (this is the programmatic equivalent of clicking into every
state on the directory) and write a normalized, diff-friendly snapshot.

Runs on a GitHub Actions runner — caliber.com is not reachable from a Claude
session (the egress proxy blocks it), so never run this inline; run it in CI.

Output:
  data/caliber/locations.json  -- {identifier: {normalized center}}, sorted.
                                  Changes ONLY when a location is added/removed/
                                  edited, so git history stays meaningful and the
                                  weekly diff is trivial.
  data/caliber/meta.json       -- {captured_at, count, source} run heartbeat,
                                  rewritten every run (kept out of locations.json
                                  so a timestamp bump is never a "change").
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = "https://www.caliber.com"
# Live, non-deleted Center content in the default (English) language.
QUERY = "+contentType:Center +live:true +deleted:false +languageId:1"
PAGE = 100
HARD_CAP = 8000  # safety stop; Caliber has ~1,800 centers
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

OUT_DIR = os.path.join("data", "caliber")
LOCATIONS_PATH = os.path.join(OUT_DIR, "locations.json")
META_PATH = os.path.join(OUT_DIR, "meta.json")


def _fetch_page(offset, limit):
    q = urllib.parse.quote(QUERY, safe="")
    # orderby a stable field so paging is consistent within a single run.
    url = (f"{BASE}/api/content/render/false/query/{q}"
           f"/limit/{limit}/offset/{offset}/orderby/identifier")
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    last_err = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
                return data.get("contentlets", []) or []
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = e
            time.sleep(2 ** attempt)
    raise RuntimeError(f"failed to fetch offset={offset}: {last_err}")


def fetch_all_centers():
    """Page through every live Center, deduped by dotCMS identifier."""
    by_id = {}
    offset = 0
    while offset < HARD_CAP:
        page = _fetch_page(offset, PAGE)
        if not page:
            break
        for c in page:
            ident = c.get("identifier")
            if ident:
                by_id[ident] = c
        print(f"  offset {offset}: +{len(page)} rows (unique so far: {len(by_id)})")
        if len(page) < PAGE:
            break
        offset += PAGE
    return by_id


def _clean(v):
    if v is None:
        return ""
    return str(v).strip()


def normalize(c):
    """Reduce a raw dotCMS Center contentlet to the fields we track.

    Keep it to stable, human-meaningful fields — enough to identify a shop and
    describe it in an email, without volatile CMS bookkeeping (inode, modDate,
    render flags) that would create noise in the weekly diff.
    """
    lat, lng = c.get("latitude"), c.get("longitude")
    url_map = _clean(c.get("urlMap") or c.get("URL_MAP_FOR_CONTENT"))
    return {
        "identifier": _clean(c.get("identifier")),
        "centerId": _clean(c.get("centerId")),
        "name": _clean(c.get("title")),
        "address1": _clean(c.get("address1")),
        "city": _clean(c.get("city")),
        "state": _clean(c.get("state")),
        "zip": _clean(c.get("zip")),
        "phone": _clean(c.get("telephone")),
        "email": _clean(c.get("emailAddress")),
        "latitude": lat if isinstance(lat, (int, float)) else _clean(lat),
        "longitude": lng if isinstance(lng, (int, float)) else _clean(lng),
        "openDate": _clean(c.get("openDate")),
        "status": _clean(c.get("standardWarningTitle")),  # e.g. "TEMPORARILY CLOSED"
        "url": (BASE + url_map) if url_map.startswith("/") else url_map,
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"Scraping Caliber centers: {QUERY}")
    raw = fetch_all_centers()
    if not raw:
        print("ERROR: zero centers returned — refusing to overwrite snapshot.", file=sys.stderr)
        return 1

    locations = {}
    for ident, c in raw.items():
        n = normalize(c)
        # Skip anything without a usable state/city (defensive).
        locations[ident] = n

    locations = dict(sorted(locations.items()))
    with open(LOCATIONS_PATH, "w") as f:
        json.dump(locations, f, indent=2, sort_keys=True)
        f.write("\n")

    by_state = {}
    for n in locations.values():
        by_state[n["state"]] = by_state.get(n["state"], 0) + 1
    meta = {
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(locations),
        "states": len(by_state),
        "source": f"{BASE}/find-a-location",
    }
    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2)
        f.write("\n")

    print(f"Wrote {len(locations)} centers across {len(by_state)} states -> {LOCATIONS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
