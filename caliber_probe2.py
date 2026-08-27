#!/usr/bin/env python3
"""ONE-TIME PROBE 3 (not part of the weekly pipeline).

We learned the individual location content type is dotCMS `Center`. This probe
tries the standard anonymous dotCMS content endpoints for +contentType:Center,
saves the responses, and prints how many centers each returns plus one sample
record's fields. It also pulls the raw /locations/ca HTML and extracts the
/locations/... link hierarchy (state -> city -> center) as a fallback path.
Whichever endpoint returns the full Center set with address/geo fields becomes
the basis for caliber_scraper.py.
"""
import json
import re
import urllib.parse
import urllib.request

OUT = "data/caliber/_discovery"
BASE = "https://www.caliber.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")


def req(url, method="GET", body=None, ctype="application/json"):
    headers = {"User-Agent": UA, "Accept": "application/json"}
    data = None
    if body is not None:
        data = body.encode() if isinstance(body, str) else json.dumps(body).encode()
        headers["Content-Type"] = ctype
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return None, f"ERROR {e}"


def summarize(tag, status, text):
    print(f"\n[{tag}] status={status} len={len(text) if text else 0}")
    fn = f"{OUT}/probe3_{tag}.json"
    open(fn, "w").write(text or "")
    try:
        d = json.loads(text)
    except Exception:
        print(f"    (non-JSON) head: {text[:300]!r}")
        return
    conts = None
    if isinstance(d, dict):
        if "contentlets" in d:
            conts = d["contentlets"]
        elif "entity" in d and isinstance(d["entity"], dict) and "jsonObjectView" in d["entity"]:
            conts = d["entity"]["jsonObjectView"].get("contentlets")
        elif "entity" in d and isinstance(d["entity"], list):
            conts = d["entity"]
    if conts is not None:
        print(f"    contentlets: {len(conts)}")
        if conts:
            print(f"    sample keys: {sorted(conts[0].keys())}")
            print(f"    sample: {json.dumps(conts[0])[:900]}")
    else:
        print(f"    top-level keys: {list(d.keys()) if isinstance(d, dict) else type(d)}")
        print(f"    head: {text[:400]}")


def main():
    q = "+contentType:Center +live:true +languageId:1"
    # 1) Classic Content REST API (path-encoded query)
    path_q = urllib.parse.quote(q, safe="")
    summarize("content_rest", *req(
        f"{BASE}/api/content/render/false/query/{path_q}/limit/3/orderby/modDate%20desc"))
    # 2) Newer _search POST (dotCMS 5.3+)
    summarize("content_search_post", *req(
        f"{BASE}/api/content/_search", "POST",
        {"query": q, "sort": "modDate desc", "limit": 3, "offset": 0}))
    # 3) ES search POST (query_string form)
    summarize("es_search_qs", *req(
        f"{BASE}/api/es/search", "POST",
        {"query": {"query_string": {"query": q}}, "size": 3, "from": 0}))
    # 4) ES search POST (dotCMS shorthand form)
    summarize("es_search_short", *req(
        f"{BASE}/api/es/search", "POST",
        {"query": q, "size": 3, "from": 0}))

    # 5) Link hierarchy from the raw CA state page
    st, html = req(f"{BASE}/locations/ca", "GET")
    print(f"\n[locations/ca html] status={st} len={len(html) if html else 0}")
    if html and html.startswith("<"):
        links = sorted(set(re.findall(r'href="(/locations/[^"#?]+)"', html)))
        open(f"{OUT}/ca_sublinks.json", "w").write(json.dumps(links, indent=2))
        print(f"    /locations/* links on CA page: {len(links)}")
        for l in links[:25]:
            print("     ", l)


if __name__ == "__main__":
    main()
