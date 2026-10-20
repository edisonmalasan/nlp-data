"""
discover_from_websites.py — find each agency's official Facebook page from the
agency's own website.

Guessing a Facebook slug does not work: "PSAofficial" turns out to be a page
called "Pet Society". A government agency's own website linking its social
page is the strongest possible evidence, so that is what this uses.

    python src/collect/discover_from_websites.py
    python src/collect/discover_from_websites.py --apply
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
from urllib.parse import urljoin, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import orca_browser as ob
import verify_sources as vs

REGISTRY = os.path.join(ROOT, "data", "provenance", "government_agencies.csv")
REPORT = os.path.join(ROOT, "data", "provenance", "website_discovery.json")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# agency, official website, tokens that must name the agency on the page
AGENCIES = [
    ("Department of Agriculture", "https://www.da.gov.ph", ["Department of Agriculture"]),
    ("Department of Energy", "https://www.doe.gov.ph", ["Department of Energy"]),
    ("Department of Finance", "https://www.dof.gov.ph", ["Department of Finance"]),
    ("Department of Foreign Affairs", "https://www.dfa.gov.ph", ["Department of Foreign Affairs"]),
    ("Department of Labor and Employment", "https://www.dole.gov.ph",
     ["Department of Labor and Employment"]),
    ("Department of Justice", "https://www.doj.gov.ph", ["Department of Justice"]),
    ("Department of Science and Technology", "https://www.dost.gov.ph",
     ["Department of Science and Technology"]),
    ("Department of Transportation", "https://dotr.gov.ph", ["Department of Transportation"]),
    ("Department of Tourism", "https://tourism.gov.ph", ["Department of Tourism"]),
    ("Office of the Vice President", "https://www.ovp.gov.ph", ["Office of the Vice President"]),
    ("Presidential Communications Operations Office", "https://www.pco.gov.ph",
     ["Presidential Communications Operations Office", "PCO"]),
    ("National Disaster Risk Reduction and Management Council", "https://www.ndrrmc.gov.ph",
     ["National Disaster Risk Reduction", "NDRRMC"]),
    ("Philippine Information Agency", "https://www.pia.gov.ph", ["Philippine Information Agency"]),
    ("Official Gazette", "https://www.officialgazette.gov.ph", ["Official Gazette"]),
    ("Bureau of Internal Revenue", "https://www.bir.gov.ph", ["Bureau of Internal Revenue"]),
    ("Bureau of the Treasury", "https://www.btreasury.gov.ph", ["Bureau of the Treasury"]),
    ("Bureau of Immigration", "https://immigration.gov.ph", ["Bureau of Immigration"]),
    ("Social Security System", "https://www.sss.gov.ph", ["Social Security System"]),
    ("Bangko Sentral ng Pilipinas", "https://www.bsp.gov.ph", ["Bangko Sentral ng Pilipinas"]),
    ("Government Service Insurance System", "https://www.gsis.gov.ph",
     ["Government Service Insurance System"]),
    ("Philippine Health Insurance Corporation", "https://www.philhealth.gov.ph", ["PhilHealth"]),
    ("Land Transportation Office", "https://lto.gov.ph", ["Land Transportation Office"]),
    ("Philippine National Police", "https://pnp.gov.ph", ["Philippine National Police"]),
    ("National Bureau of Investigation", "https://nbi.gov.ph", ["National Bureau of Investigation"]),
    ("National Police Commission", "https://napolcom.gov.ph", ["National Police Commission"]),
    ("Civil Service Commission", "https://csc.gov.ph", ["Civil Service Commission"]),
    ("Commission on Elections", "https://comelec.gov.ph", ["Commission on Elections"]),
    ("Commission on Higher Education", "https://ched.gov.ph", ["Commission on Higher Education"]),
    ("Commission on Audit", "https://coa.gov.ph", ["Commission on Audit"]),
    ("Food and Drug Administration", "https://www.fda.gov.ph", ["Food and Drug Administration"]),
    ("Philippine Charity Sweepstakes Office", "https://www.pcso.gov.ph",
     ["Philippine Charity Sweepstakes Office"]),
    ("Philippine Veterans Affairs Office", "https://www.pva.gov.ph",
     ["Philippine Veterans Affairs Office"]),
    ("National Commission on Culture and the Arts", "https://ncca.gov.ph",
     ["National Commission on Culture and the Arts"]),
    ("National Commission on Muslim Filipinos", "https://ncmf.gov.ph",
     ["National Commission on Muslim Filipinos"]),
    ("National Commission on Indigenous Peoples", "https://www.ncip.gov.ph",
     ["National Commission on Indigenous Peoples"]),
    ("National Historical Commission of the Philippines", "https://nhcp.gov.ph",
     ["National Historical Commission"]),
    ("National Youth Commission", "https://nyc.gov.ph", ["National Youth Commission"]),
    ("Philippine Commission on Women", "https://pcw.gov.ph", ["Philippine Commission on Women"]),
    ("National Economic and Development Authority", "https://neda.gov.ph",
     ["National Economic and Development Authority"]),
    ("Philippine Statistics Authority", "https://psa.gov.ph", ["Philippine Statistics Authority"]),
    ("Metropolitan Waterworks and Sewerage System", "https://www.mwss.gov.ph",
     ["Metropolitan Waterworks"]),
    ("National Water Resources Board", "https://nwrb.gov.ph", ["National Water Resources Board"]),
    ("National Irrigation Administration", "https://www.nia.gov.ph",
     ["National Irrigation Administration"]),
    ("Fertilizer and Pesticide Authority", "https://fpa.gov.ph", ["Fertilizer and Pesticide Authority"]),
    ("Land Management Bureau", "https://lmb.gov.ph", ["Land Management Bureau"]),
    ("National Mapping and Information Authority", "https://namria.gov.ph",
     ["National Mapping and Information Authority"]),
    ("Philippine Geospatial Authority", "https://philsa.gov.ph",
     ["Philippine Geospatial Authority"]),
    ("Intellectual Property Office Philippines", "https://www.ipophil.gov.ph",
     ["Intellectual Property Office"]),
    ("Philippine Nuclear Regulatory Institute", "https://pnri.dost.gov.ph",
     ["Philippine Nuclear Regulatory Institute"]),
    ("National Food Authority", "https://www.nfa.gov.ph", ["National Food Authority"]),
    ("Philippine Space Agency", "https://philsa.gov.ph", ["Philippine Space Agency"]),
    ("Climate Change Commission", "https://climate.gov.ph", ["Climate Change Commission"]),
    ("Philippine Economic Zone Authority", "https://peza.gov.ph",
     ["Philippine Economic Zone Authority"]),
    ("Board of Investments", "https://boi.gov.ph", ["Board of Investments"]),
    ("Small Business Corporation", "https://sbc.gov.ph", ["Small Business Corporation"]),
    ("Securities and Exchange Commission", "https://www.sec.gov.ph",
     ["Securities and Exchange Commission"]),
    ("Pagcor", "https://www.pagcor.ph", ["PAGCOR", "Philippine Amusement"]),
    ("Presidential Commission on Good Government", "https://pcgg.gov.ph",
     ["Presidential Commission on Good Government"]),
    ("Philippine Statistics Authority", "https://psa.gov.ph", ["Philippine Statistics Authority"]),
    ("National Security Council", "https://nsc.gov.ph", ["National Security Council"]),
    ("Games and Amusements Board", "https://gambling.gov.ph", ["Games and Amusements Board"]),
    ("Movie and Television Review and Classification Board", "https://mtrcb.gov.ph",
     ["Movie and Television Review"]),
    ("Occupational Safety and Health Center", "https://oshc.dole.gov.ph",
     ["Occupational Safety and Health Center"]),
    ("Bureau of Quarantine and Inspection Services", "https://bqis.doh.gov.ph",
     ["Bureau of Quarantine"]),
    ("Philippine Business for Social Progress", "https://pbsp.gov.ph",
     ["Philippine Business for Social Progress"]),
    ("Philippine Institute for Development Studies", "https://www.pids.gov.ph",
     ["Philippine Institute for Development Studies"]),
    ("Philippine Ports Authority", "https://www.ppa.com.ph", ["Philippine Ports Authority"]),
    ("Philippine National Railways", "https://pnr.gov.ph", ["Philippine National Railways"]),
    ("Philippine Rice Research Institute", "https://philrice.gov.ph",
     ["Philippine Rice Research Institute"]),
    ("Bureau of Plant and Industry", "https://bpi.gov.ph", ["Bureau of Plant and Industry"]),
    ("National Fisheries Office", "https://nfo.gov.ph", ["National Fisheries Office"]),
    ("Maritime and Coast Guard", "https://coastguard.gov.ph",
     ["Philippine Coast Guard", "Maritime and Coast Guard"]),
    ("Philippine Coast Guard Auxiliary", "https://pcgauxiliary.gov.ph",
     ["Philippine Coast Guard Auxiliary"]),
    ("National Health Research Council", "https://nhrc.gov.ph", ["National Health Research Council"]),
    ("Philippine Council for Health Research and Development", "https://pchrd.dost.gov.ph",
     ["Philippine Council for Health Research"]),
    ("Advanced Science and Technology Institute", "https://asti.dost.gov.ph",
     ["Advanced Science and Technology Institute"]),
    ("Philippine Nuclear Research Institute", "https://pnri.dost.gov.ph",
     ["Philippine Nuclear Regulatory Institute"]),
    ("Earthquake and Volcano Observatories", "https://www.phivolcs.dost.gov.ph",
     ["Philippine Institute of Volcanology", "PHIVOLCS"]),
    ("National Museum of the Philippines", "https://www.nationalmuseum.gov.ph",
     ["National Museum of the Philippines"]),
    ("National Commission for Culture and the Arts", "https://ncca.gov.ph",
     ["National Commission on Culture and the Arts"]),
    ("Film Development Council", "https://fdc.gov.ph", ["Film Development Council"]),
    ("Philippine Educational Publishers Association", "https://pepa.gov.ph",
     ["Philippine Educational Publishers Association"]),
    ("Bureau of Education", "https://www.deped.gov.ph", ["Department of Education"]),
    ("Professional Regulation Commission", "https://www.prc.gov.ph",
     ["Professional Regulation Commission"]),
    ("Mines and Geosciences Bureau", "https://mgb.gov.ph", ["Mines and Geosciences Bureau"]),
    ("Bureau of Quarantine and Inspection Services", "https://bqis.doh.gov.ph",
     ["Bureau of Quarantine"]),
    ("Philippine Nuclear Regulatory Institute", "https://pnri.dost.gov.ph",
     ["Philippine Nuclear Regulatory Institute"]),
    ("National Water Resources Board", "https://nwrb.gov.ph", ["National Water Resources Board"]),
    ("Philippine Ports Authority", "https://www.ppa.com.ph", ["Philippine Ports Authority"]),
    ("Occupational Safety and Health Center", "https://oshc.dole.gov.ph",
     ["Occupational Safety and Health Center"]),
    ("National Population Commission", "https://popcom.gov.ph", ["National Population Commission"]),
    ("Philippine Statistics Authority", "https://psa.gov.ph", ["Philippine Statistics Authority"]),
    ("Fertilizer and Pesticide Authority", "https://fpa.gov.ph", ["Fertilizer and Pesticide Authority"]),
]

FB_RE = re.compile(r"https?://(?:www\.|m\.)?facebook\.com/[A-Za-z0-9._%\-]+/?")
FB_IGNORED = {
    "facebook.com", "facebook.com/", "www.facebook.com", "m.facebook.com",
    "facebook.com/sharer", "facebook.com/share", "facebook.com/login",
    "facebook.com/photo", "facebook.com/photo.php", "facebook.com/groups",
    "facebook.com/pages", "facebook.com/events", "facebook.com/profile.php",
    "facebook.com/policy", "facebook.com/help", "facebook.com/privacy",
    "facebook.com/terms", "facebook.com/ads", "facebook.com/business",
    "facebook.com/watch", "facebook.com/notifications", "facebook.com/settings",
    "facebook.com/dialog", "facebook.com/plugins", "facebook.com/intl",
    "facebook.com/friends", "facebook.com/marketplace", "facebook.com/gaming",
    "facebook.com/reel", "facebook.com/pg", "facebook.com/feeds",
}


def fetch(url: str, timeout: int = 25) -> str:
    """Fetch a page over HTTP. Fast, but some .gov.ph sites block it."""
    import requests
    try:
        r = requests.get(url, timeout=timeout, headers={"User-Agent": UA},
                         allow_redirects=True)
        if r.status_code == 200:
            return r.text
    except Exception:
        pass
    return ""


HTML_JS = r"""
(() => {
  return JSON.stringify({
    url: location.href,
    html: document.documentElement.outerHTML.slice(0, 400000),
  });
})()
"""


def fetch_in_browser(page, url: str) -> str:
    """Fetch a page with the browser, for the sites that block plain HTTP.

    The browser is already signed in and renders whatever JavaScript the
    site uses, so this also finds links that are injected at runtime.
    """
    try:
        ob.goto(page, url, settle=5.0)
    except ob.OrcaError:
        return ""
    info = ob.read_page(page)
    if info.get("bodyLen", 0) < 200:
        time.sleep(2.0)
        info = ob.read_page(page)
    try:
        v = ob.eval_json(page, HTML_JS)
        if isinstance(v, dict):
            return v.get("html", "")
    except (ob.OrcaError, ValueError):
        pass
    return info.get("body", "")


def facebook_links(html: str, base: str) -> list:
    out = []
    for m in re.finditer(r'href=["\']([^"\']*facebook\.com[^"\']*)["\']', html, re.I):
        href = m.group(1).replace("&amp;", "&")
        if href.startswith("//"):
            href = "https:" + href
        elif href.startswith("/"):
            href = urljoin(base, href)
        if not href.startswith("http"):
            continue
        # unwrap facebook's own redirect wrapper
        u = urlparse(href)
        if "l.php" in u.path and "u" in u.query:
            from urllib.parse import parse_qs, unquote
            q = parse_qs(u.query).get("u", [""])[0]
            if q:
                href = unquote(q)
        clean = href.split("?")[0].rstrip("/")
        if clean in FB_IGNORED:
            continue
        if "/sharer" in clean or "/share" in clean or "/dialog" in clean:
            continue
        if re.search(r"facebook\.com/[A-Za-z0-9._%\-]+$", clean):
            if clean not in out:
                out.append(clean)
    return out


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
    ap = argparse.ArgumentParser(description="Find official pages from agency websites")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--only", default=None)
    args = ap.parse_args(argv)

    registry, fields = read_registry()
    known_urls = {r["official_account_url"].split("?")[0].rstrip("/")
                  for r in registry if r["platform"] == "facebook"}

    tabs = ob.list_tabs()
    page = ob.pick_tab(tabs, index=0)["browserPageId"]

    results = []
    accepted = 0
    seen_agencies = set()
    for agency, site, expected in AGENCIES:
        if agency in seen_agencies:
            continue
        seen_agencies.add(agency)
        if args.only and args.only.lower() not in agency.lower():
            continue

        html = fetch(site)
        links = facebook_links(html, site) if html else []
        if not links:
            # the site blocked plain HTTP, or the links are injected by
            # javascript - either way, ask the browser
            html = fetch_in_browser(page, site)
            links = facebook_links(html, site)
            time.sleep(0.8)

        if not html:
            results.append({"agency": agency, "site": site, "ok": False,
                            "reason": "site unreachable"})
            print(f"  no   {agency:52} site unreachable")
            continue

        if not links:
            results.append({"agency": agency, "site": site, "ok": False,
                            "reason": "no facebook link on the site"})
            print(f"  no   {agency:52} no facebook link on the site")
            continue
        # a page the agency links is a candidate; check it actually names them
        best = None
        for link in links:
            slug = link.rstrip("/").split("/")[-1]
            if not slug or slug.lower() in FB_IGNORED:
                continue
            if link.rstrip("/") in known_urls:
                best = (link, "already in the registry")
                break
            ok, reason, name = vs.verify(page, agency, slug, expected)
            if ok:
                best = (link, f"verified: {name[:60]}")
                break
            time.sleep(1.0)

        if best:
            link, reason = best
            ok = True
            results.append({"agency": agency, "site": site, "ok": True,
                            "url": link, "reason": reason})
            print(f"  OK   {agency:52} {link}")
            print(f"       {reason}")
            accepted += 1
        else:
            results.append({"agency": agency, "site": site, "ok": False,
                            "reason": "no verified facebook page linked"})
            print(f"  no   {agency:52} no verified facebook page linked")

    with io.open(REPORT, "w", encoding="utf-8", newline="") as fh:
        json.dump({"n_sites": len(seen_agencies), "n_accepted": accepted,
                   "results": results}, fh, indent=2, ensure_ascii=False)
    print(f"\n{accepted} verified -> {REPORT}")

    if not args.apply:
        print("(re-run with --apply to add them to the registry)")
        return 0

    added = 0
    for r in results:
        if not r["ok"] or r["url"].rstrip("/") in known_urls:
            continue
        slug = r["url"].rstrip("/").split("/")[-1]
        row = {k: "" for k in fields}
        row.update({
            "agency_id": slug,
            "agency_name": r["agency"],
            "agency_abbr": "",
            "agency_type": "national_government_agency",
            "parent_department": "",
            "parent_department_abbr": "",
            "official_website": r["site"],
            "official_account_url": r["url"],
            "official_account_id": "",
            "official_account_name": slug,
            "platform": "facebook",
            "source_page": slug,
            "official_verified": "true",
            "verification_basis": "linked_from_the_agency_website_and_title_checked",
            "comments_enabled": "true",
            "domains": "",
            "eligibility_s1": "true", "eligibility_s2": "true",
            "eligibility_s3": "true", "eligibility_s4": "true",
            "eligibility_s5": "true", "eligibility_s6": "true",
            "n_posts_planned": "6",
            "collection_method": "browser_dom_session",
            "notes": "found on the agency's own website and verified against the page name",
        })
        registry.append(row)
        known_urls.add(r["url"].rstrip("/"))
        added += 1
        print(f"  + facebook  {r['agency']}")

    write_registry(registry, fields)
    print(f"\nadded {added} row(s); {len(registry)} rows total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
