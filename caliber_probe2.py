#!/usr/bin/env python3
"""ONE-TIME PROBE 2 (not part of the weekly pipeline).

Tests whether a Caliber state directory page (/locations/<st>) server-renders
its centers into the Next.js __NEXT_DATA__ blob when fetched with a plain HTTP
GET (no browser). If yes, the production scraper can be lightweight `requests`
instead of Playwright. Saves the parsed blobs under data/caliber/_discovery/ for
inspection and prints the discovered center shape.
"""
import json
import re
import sys
import urllib.request

OUT = "data/caliber/_discovery"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

NEXT_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.status, r.read().decode("utf-8", "replace")


def find_center_arrays(obj, path="$"):
    """Yield (path, list) for lists whose items look like center records."""
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            hits += find_center_arrays(v, f"{path}.{k}")
    elif isinstance(obj, list):
        if obj and isinstance(obj[0], dict):
            keys = set(obj[0].keys())
            markers = {"address", "address1", "city", "state", "zip", "zipCode",
                       "latitude", "longitude", "phone", "centerName", "name",
                       "storeNumber", "locationName", "title"}
            if len(keys & markers) >= 3:
                hits.append((path, obj))
        for i, v in enumerate(obj):
            hits += find_center_arrays(v, f"{path}[{i}]")
    return hits


def main():
    for st in ["ca", "wy"]:
        url = f"https://www.caliber.com/locations/{st}"
        try:
            status, html = get(url)
        except Exception as e:
            print(f"[{st}] FETCH ERROR: {e}")
            continue
        print(f"[{st}] GET {url} -> {status}, {len(html)} bytes")
        m = NEXT_RE.search(html)
        if not m:
            print(f"[{st}] no __NEXT_DATA__ found")
            # save a slice so we can see what came back (bot wall?)
            open(f"{OUT}/state_{st}_raw_head.html", "w").write(html[:4000])
            continue
        data = json.loads(m.group(1))
        open(f"{OUT}/state_{st}_next.json", "w").write(json.dumps(data, indent=2))
        arrays = find_center_arrays(data)
        print(f"[{st}] __NEXT_DATA__ parsed; candidate center arrays: {len(arrays)}")
        for path, arr in sorted(arrays, key=lambda x: -len(x[1]))[:5]:
            print(f"    {path}  ->  {len(arr)} items; sample keys: {sorted(arr[0].keys())[:20]}")
            print(f"    sample item: {json.dumps(arr[0])[:600]}")


if __name__ == "__main__":
    main()
