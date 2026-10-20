"""
discover_links.py — read each agency's own Facebook page to find its other
official accounts.

A Philippine government agency's Facebook page carries a "Contact info" block
listing its official links: X, YouTube, Instagram, TikTok. Those are the
agency's own declarations, so they are a better source of truth than guessing
handles.

    python src/collect/discover_links.py
    python src/collect/discover_links.py --apply    # write the rows into the registry
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

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import orca_browser as ob

REGISTRY = os.path.join(ROOT, "data", "provenance", "government_agencies.csv")

LINKS_JS = r"""
(() => {
  const out = [];
  for (const a of document.querySelectorAll('a[href]')) {
    const href = a.href || '';
    const txt = (a.innerText || '').trim();
    if (!href) continue;
    if (/facebook\.com/i.test(href)) continue;
    out.push({href: href.split('?')[0], text: txt.slice(0, 80)});
  }
  return JSON.stringify(out);
})()
"""

# a link to x.com/twitter.com is the official X account
X_RE = re.compile(r"https?://(?:www\.|mobile\.)?(?:twitter|x)\.com/([A-Za-z0-9_]+)/?$", re.I)
YT_RE = re.compile(r"https?://(?:www\.)?youtube\.com/(?:@|c/|user/)([A-Za-z0-9_.-]+)", re.I)
RD_RE = re.compile(r"https?://(?:www\.)?reddit\.com/r/([A-Za-z0-9_-]+)", re.I)
# a facebook link whose path is the page's own "links" list
FB_LINK_RE = re.compile(r"facebook\.com/l\.php\?u=([^&\"]+)", re.I)


def unwrap(href: str) -> str:
    """Facebook wraps outbound links in l.php?u=<encoded>."""
    m = FB_LINK_RE.search(href or "")
    if m:
        from urllib.parse import unquote
        return unquote(m.group(1))
    return href or ""


def discover_for_page(page, page_url: str) -> dict:
    ob.goto(page, page_url, settle=4.0)
    time.sleep(1.5)
    links = ob.eval_json(page, LINKS_JS) or []
    found = {"x": [], "youtube": [], "reddit": []}
    for l in links:
        u = unwrap(l.get("href", ""))
        if not u:
            continue
        m = X_RE.match(u)
        if m and m.group(1).lower() not in ("home", "search", "explore", "i"):
            found["x"].append("https://x.com/" + m.group(1))
        m = YT_RE.match(u)
        if m:
            found["youtube"].append("https://www.youtube.com/@" + m.group(1))
        m = RD_RE.match(u)
        if m:
            found["reddit"].append("https://www.reddit.com/r/" + m.group(1))
    for k in found:
        found[k] = sorted(set(found[k]))
    return found


def read_registry():
    with io.open(REGISTRY, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_registry(rows, fields):
    with io.open(REGISTRY, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Find each agency's other official accounts")
    ap.add_argument("--apply", action="store_true",
                    help="add the discovered accounts to the registry")
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "provenance", "official_links.json"))
    args = ap.parse_args(argv)

    registry = read_registry()
    fields = list(registry[0].keys()) if registry else []

    tabs = ob.list_tabs()
    page = ob.pick_tab(tabs, index=0)["browserPageId"]

    seen_pages = {}
    for r in registry:
        if r["platform"] != "facebook":
            continue
        if r["official_account_url"] in seen_pages:
            continue
        seen_pages[r["official_account_url"]] = True
        print(f"\n{r['agency_abbr']}  {r['official_account_url']}")
        try:
            found = discover_for_page(page, r["official_account_url"])
        except ob.OrcaError as e:
            print(f"  failed: {e}")
            continue
        for k, v in found.items():
            print(f"  {k:8} {v}")
        seen_pages[r["official_account_url"]] = found

    io.open(args.out, "w", encoding="utf-8", newline="").write(
        json.dumps(seen_pages, indent=2, ensure_ascii=False))
    print(f"\nwrote {args.out}")

    if not args.apply:
        print("\n(re-run with --apply to add these to the registry)")
        return 0

    added = 0
    for fb_url, found in seen_pages.items():
        if not isinstance(found, dict):
            continue
        base = next((r for r in registry
                     if r["platform"] == "facebook" and r["official_account_url"] == fb_url), None)
        if base is None:
            continue
        for plat, urls in found.items():
            for u in urls:
                slug = u.rstrip("/").split("/")[-1]
                if plat == "youtube":
                    slug = base["source_page"] + "_yt"
                    source_page = base["source_page"] + "_yt"
                elif plat == "x":
                    source_page = base["source_page"] + "_x"
                else:
                    source_page = base["source_page"] + "_rd"
                if any(r["platform"] == plat and r["official_account_url"] == u
                       for r in registry):
                    continue
                row = {k: "" for k in fields}
                row.update({
                    "agency_id": base["agency_id"],
                    "agency_name": base["agency_name"],
                    "agency_abbr": base["agency_abbr"],
                    "agency_type": base["agency_type"],
                    "parent_department": base["parent_department"],
                    "parent_department_abbr": base["parent_department_abbr"],
                    "official_website": base["official_website"],
                    "official_account_url": u,
                    "official_account_id": "",
                    "official_account_name": slug,
                    "platform": plat,
                    "source_page": source_page,
                    "official_verified": "true",
                    "verification_basis": "linked_from_agency_facebook_page",
                    "comments_enabled": "true",
                    "domains": base["domains"],
                    "eligibility_s1": "true", "eligibility_s2": "true",
                    "eligibility_s3": "true", "eligibility_s4": "true",
                    "eligibility_s5": "true", "eligibility_s6": "true",
                    "n_posts_planned": "6",
                    "collection_method": "browser_dom_session",
                    "notes": "discovered from the agency's own Facebook page contact links",
                })
                registry.append(row)
                added += 1
                print(f"  + {plat:8} {u}")

    write_registry(registry, fields)
    print(f"\nadded {added} row(s) to the registry")
    return 0


if __name__ == "__main__":
    sys.exit(main())
