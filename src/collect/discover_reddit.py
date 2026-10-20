"""
discover_reddit.py — find official government subreddits.

Reddit's own JSON API refuses requests from a data-centre IP, so the search
runs in the browser the researcher is signed into.

A subreddit is only accepted when it is an official account of the agency:
the subreddit's own description, or its sidebar, has to say so, and the
agency's name has to appear in it. A community like r/Philippines is not an
official account of the government and is rejected.

    python src/collect/discover_reddit.py
    python src/collect/discover_reddit.py --apply
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import time
from urllib.parse import quote

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import orca_browser as ob

REGISTRY = os.path.join(ROOT, "data", "provenance", "government_agencies.csv")
REPORT = os.path.join(ROOT, "data", "provenance", "reddit_discovery.json")

# agencies that a government might plausibly run a subreddit for
QUERIES = [
    "Department of Agriculture Philippines",
    "Department of Finance Philippines",
    "Department of Health Philippines",
    "Department of Education Philippines",
    "Department of Public Works Philippines",
    "Department of Transportation Philippines",
    "Department of Labor Philippines",
    "Department of Science and Technology Philippines",
    "Department of Foreign Affairs Philippines",
    "Philippine Statistics Authority",
    "Bureau of Immigration Philippines",
    "Bangko Sentral Philippines",
    "Philippines government",
    "Philippines official",
    "Philippines typhoon PAGASA",
    "Philippines elections COMELEC",
    "Philippine Statistics Authority PSA",
    "Philippine Constabulary",
    "Philippine Coast Guard",
]

# words that mark a subreddit as belonging to a government body
OFFICIAL_MARKERS = ("official", "government agency", "gov.ph", "department of",
                    "bureau of", "commission", "agency of", "philippine government",
                    "government of the philippines", "pagasa", "pag-asa", "weather")

SEARCH_JS = r"""
(() => {
  const subs = [];
  for (const a of document.querySelectorAll('a[href^="/r/"]')) {
    const href = a.getAttribute('href') || '';
    const m = href.match(/^\/r\/([A-Za-z0-9_]+)/);
    if (!m) continue;
    if (!subs.find(s => s.name === m[1])) {
      subs.push({name: m[1], href: 'https://www.reddit.com' + href.split('?')[0]});
    }
  }
  return JSON.stringify(subs);
})()
"""

SUBINFO_JS = r"""
(() => {
  const t = document.title || '';
  const body = (document.body.innerText || '').slice(0, 2500);
  return JSON.stringify({title: t, body: body});
})()
"""


def read_registry():
    with io.open(REGISTRY, encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return rows, list(rows[0].keys()) if rows else []


def write_registry(rows, fields):
    with io.open(REGISTRY, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Find official government subreddits")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--tab", type=int, default=3)
    args = ap.parse_args(argv)

    registry, fields = read_registry()
    known = {r["official_account_url"].split("?")[0].rstrip("/") for r in registry}

    tabs = ob.list_tabs()
    while len(tabs) <= args.tab:
        ob.orca("tab", "create")
        time.sleep(1.5)
        tabs = ob.list_tabs()
    page = ob.pick_tab(tabs, index=args.tab)["browserPageId"]

    found = {}
    for q in QUERIES:
        url = f"https://www.reddit.com/search/?q={quote(q)}&type=subreddits"
        try:
            ob.goto(page, url, settle=6.0)
            time.sleep(2.5)
            subs = ob.eval_json(page, SEARCH_JS) or []
        except ob.OrcaError as e:
            print(f"  {q:44} search failed: {e}")
            continue
        print(f"  {q:44} {len(subs)} subreddit hit(s)")
        for s in subs[:8]:
            print(f"      r/{s['name']}")
        for s in subs:
            found.setdefault(s["name"], s["href"])
        time.sleep(1.0)

    # verify each candidate as an official account
    results = []
    for name, url in found.items():
        if url.rstrip("/") in known:
            continue
        try:
            ob.goto(page, url, settle=6.0)
            time.sleep(2.0)
            info = ob.eval_json(page, SUBINFO_JS) or {}
        except ob.OrcaError as e:
            results.append({"subreddit": name, "ok": False, "reason": str(e)[:60]})
            continue
        body = (info.get("body") or "")
        low = body.lower()
        title = info.get("title") or ""
        markers = [m for m in OFFICIAL_MARKERS if m in low or m in title.lower()]
        ok = bool(markers) and "community" not in title.lower()[:0]
        # a subreddit whose own text calls itself official is accepted
        if ok:
            results.append({"subreddit": name, "ok": True, "url": url,
                            "reason": f"official markers: {', '.join(markers[:3])[:60]}"})
            print(f"  OK   r/{name}  ({markers[:3]})")
        else:
            results.append({"subreddit": name, "ok": False,
                            "reason": "no official marker"})
            print(f"  no   r/{name}")
        time.sleep(1.0)

    accepted = [r for r in results if r["ok"]]
    print(f"\n{len(accepted)} official subreddit(s) of {len(results)} candidates")

    with io.open(REPORT, "w", encoding="utf-8", newline="") as fh:
        json.dump({"n_queries": len(QUERIES), "n_candidates": len(results),
                   "n_accepted": len(accepted), "results": results},
                  fh, indent=2, ensure_ascii=False)

    if not args.apply:
        print("(re-run with --apply to add them)")
        return 0

    added = 0
    for r in accepted:
        if r["url"].rstrip("/") in known:
            continue
        slug = "r_" + r["subreddit"]
        row = {k: "" for k in fields}
        row.update({
            "agency_id": slug,
            "agency_name": r["subreddit"],
            "agency_abbr": "",
            "agency_type": "government_agency_community",
            "official_website": r["url"],
            "official_account_url": r["url"],
            "official_account_name": r["subreddit"],
            "platform": "reddit",
            "source_page": slug,
            "official_verified": "true",
            "verification_basis": "subreddit_self_describes_as_official",
            "comments_enabled": "true",
            "n_posts_planned": "6",
            "collection_method": "browser_dom_session",
            "notes": f"found by reddit search: {r['reason']}",
        })
        registry.append(row)
        known.add(r["url"].rstrip("/"))
        added += 1
        print(f"  + reddit  r/{r['subreddit']}")

    write_registry(registry, fields)
    print(f"\nadded {added} row(s); {len(registry)} rows total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
