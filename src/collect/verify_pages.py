"""
verify_pages.py — is every registered Facebook source a GOVERNMENT page?

The name check alone is not enough. A page can be called "deped" and belong to
somebody, and a name that matches the agency's name says nothing about who
runs it. So every registered page is checked against three things Facebook
itself publishes:

  1. the page CATEGORY - a government agency page is categorised as
     "Government organization" / "Government agency" / "Government office"
  2. the page BUTTONS - a Page shows "Message" and "Follow"; a personal
     profile shows "Add Friend" and no "Message"
  3. the external WEBSITE in the Details section - a government agency links
     its own .gov.ph site

A page that fails any of them is reported with the reason, so the source
list can be corrected rather than assumed.

    python src/collect/verify_pages.py
    python src/collect/verify_pages.py --apply     # drop the failures from the registry
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
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import orca_browser as ob

REGISTRY = os.path.join(ROOT, "data", "provenance", "government_agencies.csv")
REPORT = os.path.join(ROOT, "data", "provenance", "page_governance.json")
RAW = os.path.join(ROOT, "data", "raw")

PAGE_JS = r"""
(() => {
  const clean = s => (s || '').replace(/\u00a0/g, ' ').replace(/[ \t]+/g, ' ').trim();
  const b = clean(document.body.innerText || '');
  const lines = b.split('\n').map(s => clean(s)).filter(Boolean);

  const fi = lines.findIndex(l => /followers/i.test(l) && /\d/.test(l));
  const name = fi >= 0 ? (lines[fi - 1] || '') : '';
  const followers = fi >= 0 ? lines[fi] : '';

  // the category sits a few lines after the follower count
  let category = '';
  if (fi >= 0) {
    for (let i = fi + 1; i < Math.min(fi + 8, lines.length); i++) {
      const l = lines[i];
      if (/^(Message|Follow|Search|MessageFollow|Add Friend|Add to Story|Following|Group|Learn More)$/i.test(l)) continue;
      if (l.length > 60) continue;          // a description, not a category
      if (/followers|following/i.test(l)) continue;
      category = l;
      break;
    }
  }

  const buttons = [];
  for (const l of lines) {
    if (/^(Message|Follow|Following|Add Friend|Add to Story|Group|Learn More|Subscribe)$/i.test(l)) {
      if (buttons.indexOf(l) < 0) buttons.push(l);
    }
    if (buttons.length >= 4) break;
  }

  // the external links in the Details section
  const links = [];
  for (const a of document.querySelectorAll('a[href]')) {
    const h = a.getAttribute('href') || '';
    const t = clean(a.innerText || '');
    if (!h || !/^https?:/.test(h)) continue;
    if (/facebook\.com|fb\.com|instagram|youtube|twitter|x\.com|tiktok|linkedin|pinterest/i.test(h)) continue;
    if (links.indexOf(h) < 0) links.push(h);
  }

  const blocked = /This content isn't available|You're Temporarily Blocked|Page Not Found|content is no longer available/i.test(b);

  return JSON.stringify({
    name: name, followers: followers, category: category,
    buttons: buttons, links: links.slice(0, 8),
    bodyLen: b.length, blocked: blocked,
    description: (lines[fi + 3] || (lines[fi + 2] || '')) if fi >= 0 else '',
  });
})()
"""

GOV_CATEGORY = re.compile(r"government", re.I)
GOV_DOMAIN = re.compile(r"\.gov\.ph\b", re.I)


def read_rows(path):
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_rows(path, rows, fields):
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def collected_pages():
    """Which page slug each collected post actually came from."""
    seen = {}
    for plat in ("facebook",):
        base = os.path.join(RAW, plat)
        if not os.path.isdir(base):
            continue
        for src in sorted(os.listdir(base)):
            d = os.path.join(base, src)
            if not os.path.isdir(d):
                continue
            slugs = set()
            for f in sorted(os.listdir(d)):
                if not f.endswith(".json"):
                    continue
                try:
                    s = json.load(io.open(os.path.join(d, f), encoding="utf-8"))
                except Exception:
                    continue
                for p in s.get("posts", []):
                    u = p.get("post_url", "")
                    if "facebook.com" not in u:
                        continue
                    parts = urlparse(u).path.strip("/").split("/")
                    if parts and parts[0]:
                        slugs.add(parts[0])
            if slugs:
                seen[src] = sorted(slugs)
    return seen


def classify(row, info):
    """(verdict, reasons) for one page."""
    reasons = []
    name = (info.get("name") or "").strip()
    category = (info.get("category") or "").strip()
    buttons = info.get("buttons") or []
    links = info.get("links") or []

    if info.get("blocked") or (info.get("bodyLen") or 0) < 400:
        return "UNREAD", ["the page did not render"]

    if "Add Friend" in buttons and "Message" not in buttons:
        reasons.append("looks like a personal profile, not a Page")
    if category and not GOV_CATEGORY.search(category):
        reasons.append(f"the category is {category!r}, not a government one")
    if not category:
        reasons.append("no category line was found")

    gov_links = [l for l in links if GOV_DOMAIN.search(l)]
    if not gov_links:
        reasons.append("no .gov.ph website in the Details section")

    # the name has to name the agency
    agency = (row.get("agency_name") or "").strip()
    if agency and name:
        head = agency.split()[0].lower()
        if head and head not in name.lower() and name.lower() not in agency.lower():
            reasons.append(f"the page name {name!r} does not name {agency!r}")

    if not reasons:
        return "PASS", []
    return "FAIL", reasons


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Verify that every source is a government page")
    ap.add_argument("--apply", action="store_true",
                    help="remove the failing rows from the registry")
    ap.add_argument("--tab", type=int, default=0)
    ap.add_argument("--retries", type=int, default=3)
    args = ap.parse_args(argv)

    registry = read_rows(REGISTRY)
    fields = list(registry[0].keys()) if registry else []
    fb = [r for r in registry if r["platform"] == "facebook"]
    collected = collected_pages()

    tabs = ob.list_tabs()
    while len(tabs) <= args.tab:
        ob.orca("tab", "create")
        time.sleep(1.5)
        tabs = ob.list_tabs()
    page = ob.pick_tab(tabs, index=args.tab)["browserPageId"]

    results = []
    for i, r in enumerate(fb, 1):
        url = r["official_account_url"]
        slug = r["source_page"]
        info = {}
        for attempt in range(args.retries):
            try:
                ob.goto(page, url, settle=6.0)
                ob.wait_for_content(page, ["followers", "followers"], timeout=18.0)
                time.sleep(1.5)
                info = ob.eval_json(page, PAGE_JS) or {}
            except ob.OrcaError as e:
                info = {"error": str(e)}
            if info.get("name") or info.get("blocked"):
                break
            time.sleep(2.0)

        verdict, reasons = classify(r, info)
        got = collected.get(slug, [])
        expected = urlparse(url).path.strip("/").split("/")[0]
        if got and expected not in got:
            reasons.append(f"the collected posts came from {got}, not {expected}")
            verdict = "FAIL"

        results.append({
            "source_page": slug, "url": url, "verdict": verdict,
            "reasons": reasons, "name": info.get("name", ""),
            "category": info.get("category", ""),
            "followers": info.get("followers", ""),
            "buttons": info.get("buttons", []),
            "gov_links": [l for l in (info.get("links") or []) if GOV_DOMAIN.search(l)],
            "collected_from": got,
        })
        mark = {"PASS": "ok  ", "FAIL": "FAIL", "UNREAD": "?   "}[verdict]
        print(f"  {mark} {slug:34} {str(info.get('category',''))[:26]:28} "
              f"{str(info.get('followers',''))[:22]:24} {'; '.join(reasons)[:60]}")
        time.sleep(1.0)

    n_pass = sum(1 for x in results if x["verdict"] == "PASS")
    n_fail = sum(1 for x in results if x["verdict"] == "FAIL")
    n_unread = sum(1 for x in results if x["verdict"] == "UNREAD")
    print(f"\n{n_pass} pass, {n_fail} fail, {n_unread} could not be read")

    with io.open(REPORT, "w", encoding="utf-8", newline="") as fh:
        json.dump({"n_checked": len(results), "n_pass": n_pass, "n_fail": n_fail,
                   "n_unread": n_unread, "results": results},
                  fh, indent=2, ensure_ascii=False)
    print(f"-> {REPORT}")

    if args.apply and n_fail:
        bad = {x["source_page"] for x in results if x["verdict"] == "FAIL"}
        kept = [r for r in registry if not (r["platform"] == "facebook"
                                           and r["source_page"] in bad)]
        write_rows(REGISTRY, kept, fields)
        print(f"removed {len(registry) - len(kept)} failing row(s) from the registry")
    return 0


if __name__ == "__main__":
    sys.exit(main())
