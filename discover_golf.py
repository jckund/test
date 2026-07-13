#!/usr/bin/env python3
"""One-shot probe of Kalshi's golf market structure for a tournament.

We can't reach api.elections.kalshi.com from a Claude Code web session (egress
proxy blocks it), so this runs on a GitHub Actions runner and dumps everything
we need to know to build the real golf scraper:

  * the winner event (confirms the winner series ticker + tournament title)
  * every sibling tournament in the winner series
  * the golf series catalog (so we can see the Top-N / Make-cut series names)
  * a probe of candidate tier tickers built from the winner series prefix

Output is printed to the job log (and appended to the Actions job summary).
Delete this file once the golf scraper is built from what it finds.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

API_BASE = "https://api.elections.kalshi.com/trade-api/v2"
TOURNAMENT_CODE = os.environ.get("GOLF_CODE", "THOC26")
WINNER_SERIES = os.environ.get("GOLF_WINNER_SERIES", "KXPGATOUR")
USER_AGENT = "kalshi-golf-discovery/1.0 (+https://github.com)"


def get(url: str):
    for attempt in range(4):
        try:
            time.sleep(0.3)
            req = urllib.request.Request(url, headers={
                "User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.getcode(), json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if attempt == 3:
                return e.code, None
            time.sleep(2 ** attempt)
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == 3:
                return None, {"_error": str(e)}
            time.sleep(2 ** attempt)
    return None, None


def hr(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def main() -> int:
    hr(f"1. Winner event  {WINNER_SERIES}-{TOURNAMENT_CODE}")
    code, data = get(f"{API_BASE}/events/{WINNER_SERIES}-{TOURNAMENT_CODE}"
                     f"?with_nested_markets=true")
    print(f"HTTP {code}")
    if data and "event" in data:
        ev = data["event"]
        mkts = data.get("markets") or ev.get("markets") or []
        print(f"title      : {ev.get('title')}")
        print(f"sub_title  : {ev.get('sub_title')}")
        print(f"series     : {ev.get('series_ticker')}")
        print(f"category   : {ev.get('category')}")
        print(f"markets    : {len(mkts)}")
        for m in mkts[:5]:
            print(f"   - {m.get('ticker')} | "
                  f"{m.get('yes_sub_title') or m.get('title')}")
    else:
        print(json.dumps(data, indent=2)[:1500])

    hr(f"2. All events in series {WINNER_SERIES}")
    code, data = get(f"{API_BASE}/events?series_ticker={WINNER_SERIES}&limit=200")
    print(f"HTTP {code}")
    for e in (data or {}).get("events", []) or []:
        print(f"   {e.get('event_ticker'):40s} {e.get('status'):8s} "
              f"{e.get('sub_title') or e.get('title')}")

    hr(f"3. Series metadata for {WINNER_SERIES}")
    code, data = get(f"{API_BASE}/series/{WINNER_SERIES}")
    print(f"HTTP {code}")
    if data:
        s = data.get("series", data)
        print(f"title   : {s.get('title')}")
        print(f"category: {s.get('category')}")
        print(f"tags    : {s.get('tags')}")

    hr("4. Golf series catalog (category probes)")
    seen = {}
    for params in ("category=Sports", "category=Sports&tags=Golf",
                   "category=Golf", ""):
        url = f"{API_BASE}/series/" + (f"?{params}" if params else "")
        code, data = get(url)
        series = (data or {}).get("series", []) if isinstance(data, dict) else []
        print(f"[{params or 'no params'}] HTTP {code} -> {len(series)} series")
        for s in series:
            tk = s.get("ticker") or ""
            title = (s.get("title") or "")
            hay = (tk + " " + title).lower()
            if any(k in hay for k in ("golf", "pga", "open", "masters",
                                      "cut", "top ", "tour")):
                seen[tk] = title
    for tk in sorted(seen):
        print(f"   {tk:28s} {seen[tk]}")

    hr("5. Candidate tier ticker probes")
    prefixes = [
        WINNER_SERIES, "KXPGATOUR", "KXPGA", "KXGOLF",
    ]
    suffixes = [
        "", "TOP3", "TOP5", "TOP10", "TOP20", "TOPFIVE", "TOPTEN",
        "CUT", "MAKECUT", "MISSCUT", "MC", "TOP2", "TOP4",
    ]
    tried = set()
    for p in prefixes:
        for suf in suffixes:
            series = p + suf
            if series in tried:
                continue
            tried.add(series)
            ticker = f"{series}-{TOURNAMENT_CODE}"
            code, data = get(f"{API_BASE}/events/{ticker}"
                             f"?with_nested_markets=true")
            if code == 200 and data and "event" in data:
                ev = data["event"]
                mkts = data.get("markets") or ev.get("markets") or []
                print(f"   OK  {ticker:32s} markets={len(mkts):3d}  "
                      f"{ev.get('sub_title') or ev.get('title')}")
    print("\n(done — anything not printed under section 5 returned non-200)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
