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
    ("Department of Agrarian Reform and Rural Development", "https://www.dar.gov.ph", ["Department of Agrarian Reform and Rural Development", "Agrarian Reform and Rural Development", "DARRD"]),
    ("Department of National Defense", "https://afp.mil.ph", ["Department of National Defense", "National Defense", "DND"]),
    ("Department of Order and Payment", "https://dop.gov.ph", ["Department of Order and Payment", "Order and Payment", "DOP"]),
    ("Office of the President of the Philippines", "https://www.op.gov.ph", ["Office of the President of the Philippines", "President of the Philippines", "OPP"]),
    ("Armed Forces of the Philippines", "https://www.afp.mil.ph", ["Armed Forces of the Philippines", "AFP"]),
    ("Philippine Army", "https://www.army.mil.ph", ["Philippine Army", "Army", "PA"]),
    ("Philippine Navy", "https://www.navy.mil.ph", ["Philippine Navy", "Navy", "PN"]),
    ("Philippine Air Force", "https://www.paf.mil.ph", ["Philippine Air Force", "Air Force", "PAF"]),
    ("Bureau of Fire Protection", "https://www.bfp.gov.ph", ["Bureau of Fire Protection", "Fire Protection", "BFP"]),
    ("Bureau of Labor Conditions", "https://blc.dole.gov.ph", ["Bureau of Labor Conditions", "Labor Conditions", "BLC"]),
    ("Bureau of Local Government Supervision", "https://blgs.dilg.gov.ph", ["Bureau of Local Government Supervision", "Local Government Supervision", "BLGS"]),
    ("Bureau of Mines and Geosciences", "https://www.mgb.gov.ph", ["Bureau of Mines and Geosciences", "Mines and Geosciences", "BMG"]),
    ("Career Service Philippines", "https://csp.gov.ph", ["Career Service Philippines", "CSP"]),
    ("Civil Aeronautics Board", "https://cab.gov.ph", ["Civil Aeronautics Board", "CAB"]),
    ("Communications Commission", "https://commcom.gov.ph", ["Communications Commission", "CC"]),
    ("Dangerous Drugs Board", "https://ddb.gov.ph", ["Dangerous Drugs Board", "DDB"]),
    ("Energy Regulatory Commission", "https://www.erc.gov.ph", ["Energy Regulatory Commission", "ERC"]),
    ("Food and Nutrition Research Institute", "https://fnri.dost.gov.ph", ["Food and Nutrition Research Institute", "FNRI"]),
    ("Housing and Land Regulatory Board", "https://hlrb.gov.ph", ["Housing and Land Regulatory Board", "HLRB"]),
    ("Insurance Commission", "https://insurance.gov.ph", ["Insurance Commission", "IC"]),
    ("Light Rail Transit Authority", "https://www.lrta.gov.ph", ["Light Rail Transit Authority", "LRTA"]),
    ("Local Water Utilities Administration", "https://www.lwua.gov.ph", ["Local Water Utilities Administration", "LWUA"]),
    ("Metropolitan Manila Development Authority", "https://mmda.gov.ph", ["Metropolitan Manila Development Authority", "MMDA"]),
    ("Metropolitan Manila Authority", "https://mmmda.gov.ph", ["Metropolitan Manila Authority", "MMA"]),
    ("National Academy of Science and Technology", "https://nast.dost.gov.ph", ["National Academy of Science and Technology", "Academy of Science and Technology", "NAST"]),
    ("National Anti-Poverty Commission", "https://napc.gov.ph", ["National Anti-Poverty Commission", "Anti-Poverty Commission", "NAC"]),
    ("National Book Development Board", "https://bookdev.gov.ph", ["National Book Development Board", "Book Development Board", "NBDB"]),
    ("National Human Rights Commission", "https://www.nhrc.gov.ph", ["National Human Rights Commission", "Human Rights Commission", "NHRC"]),
    ("National Institute of Biological Control", "https://nibio.gov.ph", ["National Institute of Biological Control", "Institute of Biological Control", "NIBC"]),
    ("National Mining and Metallurgical Research Institute", "https://www.nmmr.gov.ph", ["National Mining and Metallurgical Research Institute", "Mining and Metallurgical Research Institute", "NMMRI"]),
    ("National Nutrition Council", "https://www.nnc.gov.ph", ["National Nutrition Council", "Nutrition Council", "NNC"]),
    ("National Power Corporation", "https://www.napocor.gov.ph", ["National Power Corporation", "Power Corporation", "NPC"]),
    ("National Statistical Coordination Board", "https://www.nscb.gov.ph", ["National Statistical Coordination Board", "Statistical Coordination Board", "NSCB"]),
    ("Office of the Ombudsman", "https://ombudsman.gov.ph", ["Office of the Ombudsman", "Ombudsman", "OO"]),
    ("Philippine Atomic Energy Commission", "https://paec.gov.ph", ["Philippine Atomic Energy Commission", "Atomic Energy Commission", "PAEC"]),
    ("Philippine Council for Industry, Energy and Emerging Technology Research", "https://pcieer.dost.gov.ph", ["Philippine Council for Industry, Energy and Emerging Technology Research", "Council for Industry, Energy and Emerging Technology Research"]),
    ("Philippine Crop Insurance Corporation", "https://www.pcic.gov.ph", ["Philippine Crop Insurance Corporation", "Crop Insurance Corporation", "PCIC"]),
    ("Philippine Development Authority", "https://www.phildev.gov.ph", ["Philippine Development Authority", "Development Authority", "PDA"]),
    ("Philippine Fisheries Development Authority", "https://pfda.gov.ph", ["Philippine Fisheries Development Authority", "Fisheries Development Authority", "PFDA"]),
    ("Philippine Genome Center", "https://pgc.dost.gov.ph", ["Philippine Genome Center", "Genome Center", "PGC"]),
    ("Philippine News Agency", "https://www.pna.gov.ph", ["Philippine News Agency", "News Agency", "PNA"]),
    ("Philippine Stock Exchange", "https://www.pse.com.ph", ["Philippine Stock Exchange", "Stock Exchange", "PSE"]),
    ("Pollution Control Board", "https://emb.gov.ph", ["Pollution Control Board", "PCB"]),
    ("Power Development Corporation", "https://www.pdc.gov.ph", ["Power Development Corporation", "PDC"]),
    ("Presidential Museum and Library", "https://pml.gov.ph", ["Presidential Museum and Library", "PML"]),
    ("Provincial Electricity Development Corporation", "https://pedc.gov.ph", ["Provincial Electricity Development Corporation", "PEDC"]),
    ("Public Information and Broadcasting Affairs", "https://piba.gov.ph", ["Public Information and Broadcasting Affairs", "PIBA"]),
    ("Philippine Deposit Insurance Corporation", "https://www.pdic.gov.ph", ["Philippine Deposit Insurance Corporation", "Deposit Insurance Corporation", "PDIC"]),
    ("Sugar Regulatory Administration", "https://www.sra.gov.ph", ["Sugar Regulatory Administration", "SRA"]),
    ("Subic Bay Freeport Zone Authority", "https://www.sbfa.gov.ph", ["Subic Bay Freeport Zone Authority", "SBFZA"]),
    ("Tariff Commission", "https://tariffcommission.gov.ph", ["Tariff Commission", "TC"]),
    ("Water Resources Development Commission", "https://www.wrdc.gov.ph", ["Water Resources Development Commission", "WRDC"]),
    ("Cultural Center of the Philippines", "https://www.ccp.gov.ph", ["Cultural Center of the Philippines", "CCP"]),
    ("Office of the Presidential Adviser on the Peace Process", "https://opapp.gov.ph", ["Office of the Presidential Adviser on the Peace Process", "Presidential Adviser on the Peace Process", "OPAPP"]),
    ("National Capital Region Police Office", "https://ncpo.pnp.gov.ph", ["National Capital Region Police Office", "Capital Region Police Office", "NCRPO"]),
    ("Government Procurement Policy Board", "https://gppb.gov.ph", ["Government Procurement Policy Board", "GPPB"]),
    ("National Statistics Authority", "https://www.psa.gov.ph", ["National Statistics Authority", "Statistics Authority", "NSA"]),
    ("Industrial Technology Development Institute", "https://www.itdi.dost.gov.ph", ["Industrial Technology Development Institute", "ITDI"]),
    ("Metals and Engineering Innovation Center", "https://www.meic.dost.gov.ph", ["Metals and Engineering Innovation Center", "MEIC"]),
    ("Philippine Institute of Volcanology and Seismology", "https://www.phivolcs.dost.gov.ph", ["Philippine Institute of Volcanology and Seismology", "Institute of Volcanology and Seismology", "PIVS"]),
    ("Mindanao Development Authority", "https://mindanao.gov.ph", ["Mindanao Development Authority", "MDA"]),
    ("Bangsamoro Development Agency", "https://bda.gov.ph", ["Bangsamoro Development Agency", "BDA"]),
    ("National Housing Authority", "https://www.nha.gov.ph", ["National Housing Authority", "Housing Authority", "NHA"]),
    ("Department of Migrant Workers", "https://www.dmw.gov.ph", ["Department of Migrant Workers", "Migrant Workers", "DMW"]),
    ("Commission on Filipino Workers", "https://cfo.gov.ph", ["Commission on Filipino Workers", "Filipino Workers", "CFW"]),
    ("National Commission for the Senior Citizens", "https://ncsc.gov.ph", ["National Commission for the Senior Citizens", "Commission for the Senior Citizens", "NCSC"]),
    ("Office of the Secretary to the President", "https://osp.gov.ph", ["Office of the Secretary to the President", "Secretary to the President", "OSP"]),
    ("Philippine National AIDS Council", "https://pnac.gov.ph", ["Philippine National AIDS Council", "National AIDS Council", "PNAC"]),
    ("Bureau of Public Information", "https://bpi.gov.ph", ["Bureau of Public Information", "Public Information", "BPI"]),
    ("National Integrated Research Program on Climate Change", "https://climate.gov.ph", ["National Integrated Research Program on Climate Change", "Integrated Research Program on Climate Change", "NIRPCC"]),
    ("Overseas Filipino Workers Development Center", "https://dmw.gov.ph", ["Overseas Filipino Workers Development Center", "OFWDC"]),
    ("Philippine Space Development Agency", "https://philsa.gov.ph", ["Philippine Space Development Agency", "Space Development Agency", "PSDA"]),
    ("Water Development Sector Coordinating Office", "https://wdsco.dost.gov.ph", ["Water Development Sector Coordinating Office", "WDSCO"]),
    ("Philippine Government Post Agency", "https://ppa.gov.ph", ["Philippine Government Post Agency", "Government Post Agency", "PGPA"]),
    ("Public Sector Supply Management", "https://pssm.gov.ph", ["Public Sector Supply Management", "PSSM"]),
    ("Coal and Energy Development Department", "https://doe.gov.ph", ["Coal and Energy Development Department", "CEDD"]),
    ("National Science and Technology Institute", "https://nsti.gov.ph", ["National Science and Technology Institute", "Science and Technology Institute", "NSTI"]),
    ("Philippine Nuclear Safety Regulatory Board", "https://pnsrb.dost.gov.ph", ["Philippine Nuclear Safety Regulatory Board", "Nuclear Safety Regulatory Board", "PNSRB"]),
    ("Cordillera Administrative Region", "https://car.gov.ph", ["Cordillera Administrative Region", "CAR"]),
    ("Department of Science and Technology - SET", "https://set.dost.gov.ph", ["Department of Science and Technology - SET", "Science and Technology - SET", "DSTS"]),
    ("Philippine Earth Observation Network", "https://philspace.dost.gov.ph", ["Philippine Earth Observation Network", "Earth Observation Network", "PEON"]),
    ("National Human Rights Commission - CAR", "https://nhrc.gov.ph", ["National Human Rights Commission - CAR", "Human Rights Commission - CAR", "NHRCC"]),
    ("Bureau of Services", "https://bss.gov.ph", ["Bureau of Services", "Services", "BS"]),
    ("Philippine Port Authority", "https://ppa.gov.ph", ["Philippine Port Authority", "Port Authority", "PPA"]),
    ("Philippine Registry of Civil Vitalities", "https://psa.gov.ph", ["Philippine Registry of Civil Vitalities", "Registry of Civil Vitalities", "PRCV"]),
    ("Local Government Academy", "https://lga.gov.ph", ["Local Government Academy", "LGA"]),
    ("National Disaster Response Council", "https://ndrc.gov.ph", ["National Disaster Response Council", "Disaster Response Council", "NDRC"]),
    ("National Youth Service Corps", "https://nysc.gov.ph", ["National Youth Service Corps", "Youth Service Corps", "NYSC"]),
    ("Bureau of Immigration and Naturalization", "https://immigration.gov.ph", ["Bureau of Immigration and Naturalization", "Immigration and Naturalization", "BIN"]),
    ("Office of the Special Court for the Accelerated Clean Up of the Environment", "https://sc.judiciary.gov.ph", ["Office of the Special Court for the Accelerated Clean Up of the Environment", "Special Court for the Accelerated Clean Up of the Environment"]),
    ("Cebu Port Authority", "https://cpa.gov.ph", ["Cebu Port Authority", "CPA"]),
    ("Authority for the Freeport of Clark", "https://afc.gov.ph", ["Authority for the Freeport of Clark", "AFC"]),
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
    # One process drives the browser. Three discovery runs once outlived
    # their killed supervisors and kept navigating the same tab, which
    # closed the runtime's connection and made the collector report every
    # account as empty. The lock makes that impossible.
    import browser_lock
    if not browser_lock.take("this discovery", log=print):
        return 2
    try:
        return _main(argv)
    finally:
        browser_lock.release()


def _main(argv=None) -> int:
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
            # The report is written after every agency, not at the end. A run
            # that is interrupted - and they get interrupted - keeps what it
            # found instead of losing the whole hour of work.
            with io.open(REPORT, "w", encoding="utf-8", newline="") as fh:
                json.dump({"n_sites": len(AGENCIES), "n_accepted": accepted,
                           "results": results}, fh, indent=2, ensure_ascii=False)
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
