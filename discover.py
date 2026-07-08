#!/usr/bin/env python3
"""One-shot: discover all Kalshi events for this NASCAR race.

The race page groups several markets (winner, top 3/5/10/20). Each is a
separate Kalshi event. This finds them by scanning NASCAR series and matching
events for this race, then writes data/discovery.json for inspection.
"""
import json
import os
import sys
import urllib.request

API = "https://api.elections.kalshi.com/trade-api/v2"
WINNER = "KXNASCARRACE-QUAS4AA26"
RACE_CODE = WINNER.split("-", 1)[1]          # "QUAS4AA26"
RACE_NAME = "quaker state 400"               # matches titles across series
UA = "nascar-discover/1.0"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def paged(url):
    """Yield items across cursor pagination for a list endpoint."""
    cursor = None
    while True:
        u = url + (("&" if "?" in url else "?") + f"cursor={cursor}" if cursor else "")
        data = get(u)
        yield data
        cursor = data.get("cursor")
        if not cursor:
            break


def main():
    nascar_series = []
    try:
        for page in paged(f"{API}/series?category=Sports"):
            for s in page.get("series", []):
                blob = (s.get("ticker", "") + " " + s.get("title", "")).upper()
                if "NASCAR" in blob:
                    nascar_series.append(s.get("ticker"))
    except Exception as e:
        print(f"series listing failed: {e}", file=sys.stderr)

    # Always include the known winner series as a safety net.
    if "KXNASCARRACE" not in nascar_series:
        nascar_series.append("KXNASCARRACE")
    nascar_series = sorted(set(filter(None, nascar_series)))
    print(f"NASCAR series: {nascar_series}", file=sys.stderr)

    found = {}
    for st in nascar_series:
        try:
            for page in paged(f"{API}/events?series_ticker={st}&with_nested_markets=false"):
                for ev in page.get("events", []):
                    et = ev.get("event_ticker", "")
                    title = ev.get("title", "") or ""
                    if RACE_CODE in et or RACE_NAME in title.lower():
                        found[et] = {
                            "event_ticker": et,
                            "series_ticker": st,
                            "title": title,
                            "sub_title": ev.get("sub_title"),
                        }
        except Exception as e:
            print(f"events failed for {st}: {e}", file=sys.stderr)

    # Directly probe the specific top-N tiers the user asked about, in case
    # a series was missed by the category scan.
    for n in (2, 3, 5, 10, 15, 20, 25):
        et = f"KXNASCARTOP{n}-{RACE_CODE}"
        if et in found:
            continue
        try:
            data = get(f"{API}/events/{et}?with_nested_markets=false")
            ev = data.get("event", {})
            if ev.get("event_ticker"):
                found[et] = {
                    "event_ticker": et,
                    "series_ticker": ev.get("series_ticker", f"KXNASCARTOP{n}"),
                    "title": ev.get("title"),
                    "sub_title": ev.get("sub_title"),
                    "probed": True,
                }
                print(f"probe hit: {et}", file=sys.stderr)
        except Exception as e:
            print(f"probe miss: {et} ({e})", file=sys.stderr)

    result = sorted(found.values(), key=lambda x: x["event_ticker"])
    os.makedirs("data", exist_ok=True)
    with open("data/discovery.json", "w") as f:
        json.dump(result, f, indent=2)
    print(json.dumps(result, indent=2))
    print(f"\nDiscovered {len(result)} events for {RACE_CODE}", file=sys.stderr)


if __name__ == "__main__":
    main()
