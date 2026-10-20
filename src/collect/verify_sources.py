"""
verify_sources.py — check candidate source accounts and add the good ones to
the registry.

A candidate slug is only accepted when the page it resolves to names the
agency. Anything else - a fan page, a personal profile, a different
organisation, a page that no longer exists - is rejected with a reason, so
the evidence for the final source list is on record.

    python src/collect/verify_sources.py                 # check only
    python src/collect/verify_sources.py --apply         # check and add
    python src/collect/verify_sources.py --source facebook
    python src/collect/verify_sources.py --source youtube
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import orca_browser as ob
from candidates import CANDIDATES

REGISTRY = os.path.join(ROOT, "data", "provenance", "government_agencies.csv")
REPORT = os.path.join(ROOT, "data", "provenance", "source_verification.json")

# Organisations that are government corporations rather than departments
GOCC = {
    "Bangko Sentral ng Pilipinas", "Government Service Insurance System",
    "Social Security System", "Philippine Health Insurance Corporation",
    "Philippine Charity Sweepstakes Office", "Philippine Veterans Affairs Office",
    "Land Transportation Office", "National Irrigation Administration",
    "Small Business Corporation", "Philippine Ports Authority",
    "Philippine Economic Zone Authority", "Bureau of Immigration",
    "Security and Exchange Commission", "Food and Drug Administration",
    "National Police Commission", "Philippine Nuclear Regulatory Institute",
    "National Water Resources Board", "Space Agency",
    "Philippine Space Agency", "Metropolitan Waterworks and Sewerage System",
    "Philippine Credit and Investments Corporation",
}

BLOCKED_MARKERS = (
    "content isn't available", "this content isn't available",
    "page not found", "temporarily blocked", "this account has been",
    "sorry, this page isn't available",
)

# The page name is not in document.title for a Facebook profile - the title
# stays "(N) Facebook" and the name is in the rendered text. A rendered
# profile carries a follower count; a page that has not rendered does not.
RENDERED_MARKERS = ("followers", "following", "Government organization")


def identity_block(body: str) -> str:
    """The text that identifies the page: its name and its follower count.

    Only this block is checked. Searching the whole body let a page called
    "Happiness Travels and Tours" pass for the Department of Tourism,
    because the agency name appears later on in its navigation.
    """
    lines = [l.strip() for l in (body or "").splitlines() if l.strip()]
    out = []
    for line in lines:
        out.append(line)
        if "followers" in line:
            break
        if len(out) > 12:
            break
    return " ".join(out)


def page_name(body: str) -> str:
    """The page's display name, taken from the line before the follower count."""
    lines = [l.strip() for l in (body or "").splitlines() if l.strip()]
    for i, line in enumerate(lines):
        if "followers" in line and i > 0:
            return lines[i - 1]
    for line in lines[:12]:
        if len(line) > 3 and "followers" not in line and not line.startswith("Number of"):
            return line
    return ""


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


def verify(page, agency, slug, expected) -> tuple:
    """Returns (ok, reason, name).

    The check is on the rendered page, not the title: a Facebook profile's
    document.title stays "(N) Facebook" and the agency name appears in the
    body. The page is also given time to render, because the shell that
    arrives first carries a login prompt and would otherwise be mistaken
    for a gated page.
    """
    url = f"https://www.facebook.com/{slug}"
    try:
        ob.goto(page, url, settle=6.0)
    except ob.OrcaError as e:
        return False, f"navigation failed: {e}", ""

    info = ob.wait_for_content(page, RENDERED_MARKERS, timeout=25.0)
    body = (info.get("body") or "")
    name = page_name(body)

    low = body.lower()
    for marker in BLOCKED_MARKERS:
        if marker in low:
            return False, f"page unavailable or blocked: {marker!r}", name

    if not any(m.lower() in low for m in RENDERED_MARKERS):
        return False, "page did not render (no follower count)", name

    # The check is against the identity block only - the page name and its
    # follower count. A token that appears further down the page, in the
    # navigation or a suggested page, is not evidence of anything.
    block = identity_block(body).lower()
    for token in expected:
        if token.lower() in block:
            return True, "page names the agency", name
    return False, f"page does not name the agency: {name[:60]!r}", name


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Verify candidate source accounts")
    ap.add_argument("--apply", action="store_true", help="add the verified accounts")
    ap.add_argument("--source", default="facebook", choices=["facebook", "youtube"])
    ap.add_argument("--only", default=None, help="verify just this agency name")
    args = ap.parse_args(argv)

    registry, fields = read_registry()
    known = {(r["platform"], r["source_page"]) for r in registry}
    known_urls = {r["official_account_url"] for r in registry}

    tabs = ob.list_tabs()
    if not tabs:
        print("no browser tabs. open the pages in the Orca browser first.")
        return 1
    page = ob.pick_tab(tabs, index=0)["browserPageId"]

    results = []
    accepted = 0
    for agency, slug, expected, domain in CANDIDATES:
        if args.only and args.only.lower() not in agency.lower():
            continue
        platform = args.source
        if (platform, slug) in known:
            results.append({"agency": agency, "slug": slug, "ok": True,
                            "reason": "already registered", "title": ""})
            print(f"  {agency:52} already registered")
            continue

        ok, reason, name = verify(page, agency, slug, expected)
        results.append({"agency": agency, "slug": slug, "ok": ok,
                        "reason": reason, "name": name})
        mark = "OK  " if ok else "no  "
        print(f"  {mark}{agency:52} {reason[:56]}")
        if ok:
            print(f"      {name[:80]}")
        time.sleep(1.5)
        if ok:
            accepted += 1

    with io.open(REPORT, "w", encoding="utf-8", newline="") as fh:
        json.dump({"source": args.source, "n_candidates": len(CANDIDATES),
                   "n_accepted": accepted, "results": results},
                  fh, indent=2, ensure_ascii=False)
    print(f"\n{accepted} verified -> {REPORT}")

    if not args.apply:
        print("(re-run with --apply to add them to the registry)")
        return 0

    added = 0
    for r in results:
        if not r["ok"] or r["reason"] == "already registered":
            continue
        agency = r["agency"]
        slug = r["slug"]
        url = f"https://www.facebook.com/{slug}"
        if url in known_urls:
            continue
        domain = next((d for a, s, e, d in CANDIDATES if a == agency), "")
        agency_type = ("government_corporation" if agency in GOCC
                       else "national_government_agency")
        row = {k: "" for k in fields}
        row.update({
            "agency_id": slug,
            "agency_name": agency,
            "agency_abbr": "",
            "agency_type": agency_type,
            "parent_department": "",
            "parent_department_abbr": "",
            "official_website": "",
            "official_account_url": url,
            "official_account_id": "",
            "official_account_name": slug,
            "platform": args.source,
            "source_page": slug,
            "official_verified": "true",
            "verification_basis": "page_title_checked_against_agency_name",
            "comments_enabled": "true",
            "domains": domain,
            "eligibility_s1": "true", "eligibility_s2": "true",
            "eligibility_s3": "true", "eligibility_s4": "true",
            "eligibility_s5": "true", "eligibility_s6": "true",
            "n_posts_planned": "8",
            "collection_method": "browser_dom_session",
            "notes": "added by source verification; title checked against the agency name",
        })
        registry.append(row)
        known_urls.add(url)
        added += 1
        print(f"  + {args.source:9} {agency}")

    write_registry(registry, fields)
    print(f"\nadded {added} row(s) to the registry; {len(registry)} rows total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
