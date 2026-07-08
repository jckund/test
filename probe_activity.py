#!/usr/bin/env python3
"""One-shot: probe Kalshi's trades ("Recent Activity") endpoint so we know its
shape and whether it can filter by event vs. per-market. Writes
data/probe_activity.json for inspection. Safe to delete afterwards.
"""
import json
import os
import urllib.request

API = "https://api.elections.kalshi.com/trade-api/v2"
EVENT = "KXNASCARRACE-QUAS4AA26"
MARKET = "KXNASCARRACE-QUAS4AA26-KYLA"  # Kyle Larson (known to exist)
UA = "nascar-probe/1.0"


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return {"status": r.status, "body": json.loads(r.read().decode("utf-8"))}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}


def trim(resp, n=3):
    """Keep the response but truncate the trades list for readability."""
    if "body" in resp and isinstance(resp["body"], dict):
        b = resp["body"]
        for key in ("trades",):
            if isinstance(b.get(key), list):
                b[key + "_count"] = len(b[key])
                b[key] = b[key][:n]
    return resp


out = {
    "by_market": trim(get(f"{API}/markets/trades?ticker={MARKET}&limit=10")),
    "by_event": trim(get(f"{API}/markets/trades?event_ticker={EVENT}&limit=10")),
    "no_filter": trim(get(f"{API}/markets/trades?limit=5")),
}
os.makedirs("data", exist_ok=True)
with open("data/probe_activity.json", "w") as f:
    json.dump(out, f, indent=2)
print(json.dumps(out, indent=2))
