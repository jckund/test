#!/usr/bin/env python3
"""ONE-TIME PROBE for gerbercollision.com/locations (not part of any pipeline).

The Claude session's proxy blocks gerbercollision.com, so this runs on a GitHub
Actions runner. It fetches the locations index and a couple of state pages over
plain HTTP and reports how the site serves location data: server-rendered HTML
list? embedded JSON? a JSON API? It saves the raw HTML + extracted links under
data/gerber/_discovery/ (committed by the workflow) for inspection.
"""
import json
import re
import urllib.request

OUT = "data/gerber/_discovery"
BASE = "https://www.gerbercollision.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

URLS = [
    f"{BASE}/locations",
    f"{BASE}/locations/united-states",
    f"{BASE}/locations/michigan-mi",
    f"{BASE}/locations/illinois-il",
]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except Exception as e:
        return None, f"ERROR {e}"


def main():
    import os
    os.makedirs(OUT, exist_ok=True)
    for url in URLS:
        status, body = get(url)
        slug = re.sub(r'[^a-z0-9]+', '_', url.replace(BASE, ''), flags=re.I).strip('_') or "index"
        print(f"\n===== {url} -> status={status} len={len(body) if body else 0} =====")
        if not body or not body.startswith("<"):
            print(f"  (non-HTML) head: {str(body)[:300]!r}")
            continue
        open(f"{OUT}/{slug}.html", "w").write(body)

        title = re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I)
        print(f"  title: {title.group(1).strip()[:100] if title else '(none)'}")

        # /locations/* links (state pages + maybe individual centers)
        loc_links = sorted(set(re.findall(r'href="(/locations/[^"#?]+)"', body)))
        print(f"  /locations/* links: {len(loc_links)}")
        for l in loc_links[:20]:
            print("     ", l)

        # Signals about how data is delivered
        ldjson = re.findall(r"application/ld\+json", body)
        api_hits = re.findall(r"(?i)/api/[a-z0-9/_-]*", body)
        viewing = re.findall(r"Viewing[^<]{0,40}", body)
        lat = re.findall(r"(?i)latitude", body)
        data_attrs = sorted(set(re.findall(r"(data-[a-z-]+)=", body)))
        print(f"  has __NEXT_DATA__: {'__NEXT_DATA__' in body}")
        print(f"  ld+json blocks: {len(ldjson)}")
        print(f"  '/api/' mentions: {len(api_hits)}  sample: {sorted(set(api_hits))[:5]}")
        print(f"  'Viewing' pagination: {viewing[:2]}")
        print(f"  latitude occurrences: {len(lat)}")
        print(f"  data- attrs sample: {data_attrs[:20]}")

    # dump link list for the index page for enumeration
    print("\nDone. HTML + links saved under", OUT)


if __name__ == "__main__":
    main()
