#!/usr/bin/env python3
"""Diff the freshly-scraped Caliber snapshot against the committed baseline and
build the weekly email.

Run AFTER caliber_scraper.py and BEFORE committing: the working-tree
data/caliber/locations.json is this week's scrape, while `git show HEAD:...`
is last week's committed snapshot. Locations are identified by their stable
dotCMS `identifier`, so:
    added   = ids present now but not in the baseline   (new locations)
    removed = ids present in the baseline but not now   (removed locations)

Outputs (for the workflow):
  - email_body.html / email_subject.txt   (the message to send)
  - data/caliber/changes.jsonl            (appended: one row per week with a change)
  - GITHUB_OUTPUT: changed, added, removed, total, subject

First run (no baseline committed yet) seeds silently: changed=false, no email.
"""
import html
import json
import os
import subprocess
import sys
from datetime import datetime, timezone

LOCATIONS_PATH = os.path.join("data", "caliber", "locations.json")
CHANGES_PATH = os.path.join("data", "caliber", "changes.jsonl")
BODY_PATH = "email_body.html"
SUBJECT_PATH = "email_subject.txt"
TO_DEFAULT = "justin@vivecollision.com"


def load_current():
    with open(LOCATIONS_PATH) as f:
        return json.load(f)


def load_baseline():
    """Previous committed locations.json, or None if this is the first run."""
    r = subprocess.run(["git", "show", f"HEAD:{LOCATIONS_PATH}"],
                       capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return None


def set_output(**kv):
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        for k, v in kv.items():
            print(f"[output] {k}={v}")
        return
    with open(path, "a") as f:
        for k, v in kv.items():
            f.write(f"{k}={v}\n")


def fmt_line_html(loc):
    name = html.escape(loc.get("name") or "(unnamed)")
    addr = html.escape(", ".join(p for p in [
        loc.get("address1"), loc.get("city"),
        f"{loc.get('state','')} {loc.get('zip','')}".strip()] if p))
    cid = html.escape(loc.get("centerId") or "")
    phone = html.escape(loc.get("phone") or "")
    url = html.escape(loc.get("url") or "")
    status = html.escape(loc.get("status") or "")
    bits = [f"<strong>{name}</strong>"]
    if cid:
        bits.append(f'<span style="color:#888">#{cid}</span>')
    if status:
        bits.append(f'<span style="color:#b00020">[{status}]</span>')
    line = " ".join(bits)
    sub = addr
    if phone:
        sub += f" &middot; {phone}"
    if url:
        sub = f'<a href="{url}" style="color:#1a5fb4;text-decoration:none">{sub}</a>'
    return f'<li style="margin:6px 0">{line}<br><span style="color:#555;font-size:13px">{sub}</span></li>'


def group_by_state(locs):
    out = {}
    for loc in locs:
        out.setdefault(loc.get("state") or "??", []).append(loc)
    for st in out:
        out[st].sort(key=lambda l: (l.get("city") or "", l.get("name") or ""))
    return dict(sorted(out.items()))


def section_html(title, color, locs):
    if not locs:
        return ""
    parts = [f'<h2 style="font-size:17px;color:{color};margin:22px 0 8px">{title} ({len(locs)})</h2>']
    for st, items in group_by_state(locs).items():
        parts.append(f'<h3 style="font-size:14px;color:#333;margin:14px 0 4px">{html.escape(st)} '
                     f'<span style="color:#999;font-weight:normal">({len(items)})</span></h3>')
        parts.append('<ul style="list-style:none;padding-left:0;margin:0">')
        parts.extend(fmt_line_html(l) for l in items)
        parts.append('</ul>')
    return "\n".join(parts)


def build_email(added, removed, total, when):
    week = when.strftime("%Y-%m-%d")
    quiet = not added and not removed
    if quiet:
        subject = f"Caliber locations: no changes this week ({total:,} tracked)"
    else:
        subject = f"Caliber locations: +{len(added)} new, −{len(removed)} removed (week of {week})"
    head = f"""<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:680px;margin:0 auto;color:#1a1a1a">
<h1 style="font-size:20px;margin:0 0 4px">Caliber Collision — weekly location changes</h1>
<p style="color:#666;margin:0 0 16px;font-size:14px">Week of {week} &middot; {total:,} locations tracked</p>
<p style="font-size:15px;margin:0 0 8px">
<strong style="color:#1a7f37">{len(added)}</strong> new &nbsp;|&nbsp;
<strong style="color:#b00020">{len(removed)}</strong> removed
</p>"""
    if quiet:
        body = ('<p style="font-size:15px;margin:8px 0 0">No new or removed locations this week — '
                'the full set is unchanged from last week.</p>')
    else:
        body = section_html("New locations", "#1a7f37", added)
        body += section_html("Removed locations", "#b00020", removed)
    foot = f"""<hr style="border:none;border-top:1px solid #eee;margin:24px 0 10px">
<p style="color:#999;font-size:12px;margin:0">
Source: <a href="https://www.caliber.com/find-a-location" style="color:#999">caliber.com/find-a-location</a>
&middot; generated {when.strftime('%Y-%m-%d %H:%M UTC')} by the caliber_locations GitHub Action.
</p></div>"""
    return subject, head + body + foot


def main():
    when = datetime.now(timezone.utc)
    current = load_current()
    baseline = load_baseline()

    if baseline is None:
        # First run on a fresh branch: everything would look "new", so seed the
        # baseline silently. Weekly heartbeat emails start from the next run.
        print("No committed baseline yet — seeding silently (no email).")
        set_output(send="false", changed="false", added="0", removed="0",
                   total=str(len(current)), subject="")
        return 0

    cur_ids = set(current)
    base_ids = set(baseline)
    added = [current[i] for i in cur_ids - base_ids]
    removed = [baseline[i] for i in base_ids - cur_ids]
    changed = bool(added or removed)

    # Always build + send a weekly email (heartbeat when nothing changed).
    subject, body = build_email(added, removed, len(current), when)
    with open(BODY_PATH, "w") as f:
        f.write(body)
    with open(SUBJECT_PATH, "w") as f:
        f.write(subject)

    # Only log weeks that actually changed — heartbeats aren't history.
    if changed:
        row = {
            "week": when.strftime("%Y-%m-%d"),
            "captured_at": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "added": sorted(f"{l.get('name')} ({l.get('city')}, {l.get('state')})" for l in added),
            "removed": sorted(f"{l.get('name')} ({l.get('city')}, {l.get('state')})" for l in removed),
            "total": len(current),
        }
        with open(CHANGES_PATH, "a") as f:
            f.write(json.dumps(row) + "\n")

    print(f"{subject}")
    for l in added:
        print(f"  + {l.get('name')} ({l.get('city')}, {l.get('state')})")
    for l in removed:
        print(f"  - {l.get('name')} ({l.get('city')}, {l.get('state')})")

    set_output(send="true", changed="true" if changed else "false",
               added=str(len(added)), removed=str(len(removed)),
               total=str(len(current)), subject=subject)
    return 0


if __name__ == "__main__":
    sys.exit(main())
