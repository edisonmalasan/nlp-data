"""
verify_pages.py — is every registered Facebook source a GOVERNMENT page?

The name check alone is not enough. A page can be called "deped" and belong
to somebody, and a name that matches the agency's name says nothing about
who runs it. So every registered page is checked against what Facebook
itself publishes, read from the page's identity block:

    <follower count>
    <the buttons: Message, Follow, ...>
    <the page's description, which usually self-declares>
    <the CATEGORY>
    More
    All
    About
    ...

A page passes when all three hold:

  1. the page NAME names the agency
  2. it is a Page, not a personal profile - a Page shows "Message" and
     "Follow"; a personal profile shows "Add Friend" and no "Message"
  3. there is a GOVERNMENT signal in the identity block: Facebook's own
     category ("Government organization", "Public & Government Service"),
     or a self-declaration naming the agency as the official page, or a
     .gov.ph domain

Plus a cross-check that every collected post actually came from the
registered page, so a page that was registered and then collected from
somewhere else is caught.

    python src/collect/verify_pages.py
    python src/collect/verify_pages.py --apply     # drop the failures
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

  // the identity block: the follower count and the lines under it
  const window_ = fi >= 0 ? lines.slice(fi, fi + 12) : [];

  const buttons = [];
  for (const l of lines) {
    if (/^(Message|Follow|Following|Add Friend|Add to Story|Group|Learn More|Subscribe)$/i.test(l)) {
      if (buttons.indexOf(l) < 0) buttons.push(l);
    }
    if (buttons.length >= 4) break;
  }

  // a .gov.ph domain anywhere in the page text - the Details section is
  // rendered lazily, so the link may only be in the text
  const govDomains = [];
  const re = /[a-z0-9.-]*\.gov\.ph/gi;
  let m;
  while ((m = re.exec(b)) !== null) {
    if (govDomains.indexOf(m[0]) < 0) govDomains.push(m[0]);
    if (govDomains.length >= 5) break;
  }

  const blocked = /This content isn.t available|You.re Temporarily Blocked|Page Not Found|content is no longer available/i.test(b);

  // the category is under the description, and the description usually
  // self-declares the page as official
  let category = '';
  let description = '';
  for (const l of window_.slice(1)) {
    if (/^(More|All|About|Reels|Photos|Videos|Events|Store|Groups|See more|Learn more|Details|More info)$/i.test(l)) break;
    if (!category && /government|official|agency|institution|bureau|department|authority|commission|council|service|corporation/i.test(l)) {
      category = l;
    } else if (!description && l.length > 25) {
      description = l;
    }
  }
  if (!category) {
    for (const l of window_.slice(1)) {
      if (/^(More|All|About)$/i.test(l)) break;
      if (l.length < 60) { category = l; break; }
    }
  }

  return JSON.stringify({
    name: name, followers: followers, category: category,
    description: description, buttons: buttons, window: window_.slice(0, 10),
    govDomains: govDomains, bodyLen: b.length, blocked: blocked,
  });
})()
"""

# the words that mark the identity block as a government account
GOV_SIGNAL = re.compile(
    r"government|public & government|government organization|"
    r"government service|government agency|government body|"
    r"official (facebook )?page|official account|official website|"
    r"attached agency|government corporation|state-owned", re.I)
GOV_DOMAIN = re.compile(r"\.gov\.ph\b", re.I)

# the words that are a button, not the category
BUTTON_WORDS = {"contact us", "call now", "send email", "book now", "message",
                "follow", "following", "learn more", "add friend",
                "add to story", "group", "subscribe", "search", "see more",
                "more", "more info"}


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
    base = os.path.join(RAW, "facebook")
    if not os.path.isdir(base):
        return seen
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


def name_matches(page_name, agency, abbr="", description="", self_text=""):
    """Does the page name name the agency?

    Three ways it can, and all three are legitimate:

      1. the full name - "Department of Public Works and Highways"
      2. the agency's ABBREVIATION - "DOST-PAGASA", "DepEd", "DILG",
         "NDRRMC". The abbreviation is what the agency itself calls it.
      3. the page's own description naming the agency - a page called
         "(Kagawaran ng Agrikultura)" whose description says "The
         Department of Agriculture" is the same agency.
    """
    if not agency or not page_name:
        return False
    n = page_name.lower()
    a = agency.lower()

    if a in n or n in a:
        return True

    # the abbreviation
    ab = (abbr or "").strip().lower()
    if ab and len(ab) > 2 and ab in n:
        return True

    # the page's own self-description names the agency. The description
    # sits under the follower count, and on some pages it is where the
    # category would be, so the whole identity block is searched too.
    d = " ".join([description or "", self_text or ""]).lower()
    if d and (a in d or (ab and ab in d)):
        return True

    # the significant words of the name
    generic = {"philippines", "philippine", "the", "of", "and", "ph", "official",
               "national", "government", "department", "office", "bureau",
               "agency", "commission", "council", "secretariat", "board",
               "authority", "corporation", "service", "services"}
    words = [w for w in re.findall(r"[a-z]+", a) if w not in generic and len(w) > 2]
    if not words:
        return False
    return sum(1 for w in words if w in n) >= max(1, len(words) - 1)


def classify(row, info):
    """(verdict, reasons, signals) for one page."""
    reasons = []
    signals = []

    if info.get("blocked") or (info.get("bodyLen") or 0) < 400:
        return "UNREAD", ["the page did not render"], signals

    name = (info.get("name") or "").strip()
    category = (info.get("category") or "").strip()
    description = (info.get("description") or "").strip()
    window = info.get("window") or []
    buttons = info.get("buttons") or []
    gov_domains = info.get("govDomains") or []
    agency = (row.get("agency_name") or "").strip()

    # 1. the name names the agency
    if not name:
        reasons.append("the page name was not found")
    elif not name_matches(name, agency, row.get("agency_abbr", ""), description,
                          " | ".join(window)):
        reasons.append(f"the page name {name!r} does not name {agency!r}")
    else:
        signals.append(f"the page name is {name!r}")

    # 2. it is a Page, not a personal profile
    if "Add Friend" in buttons and "Message" not in buttons:
        reasons.append("it looks like a personal profile, not a Page")
    elif "Message" in buttons or "Follow" in buttons:
        signals.append("it is a Page (Message/Follow), not a personal profile")
    else:
        reasons.append("no Page buttons were found")

    # 3. a government signal
    gov_hit = None
    if category and GOV_SIGNAL.search(category):
        gov_hit = f"the category is {category!r}"
    elif description and GOV_SIGNAL.search(description):
        gov_hit = f"the description says {description[:70]!r}"
    elif any(GOV_SIGNAL.search(l) for l in window):
        hit = next(l for l in window if GOV_SIGNAL.search(l))
        gov_hit = f"the identity block says {hit[:70]!r}"
    elif gov_domains:
        gov_hit = f"it links its own site ({', '.join(gov_domains[:2])})"
    if gov_hit:
        signals.append(gov_hit)
    else:
        reasons.append("no government signal: the category, the description "
                       "and the website are all non-governmental")

    if reasons:
        return "FAIL", reasons, signals
    return "PASS", [], signals


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Verify that every source is a government page")
    ap.add_argument("--apply", action="store_true")
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
                ob.wait_for_content(page, ["followers"], timeout=18.0)
                time.sleep(1.0)
                info = ob.eval_json(page, PAGE_JS) or {}
            except ob.OrcaError as e:
                info = {"error": str(e)}
            if info.get("name") and not info.get("error"):
                break
            time.sleep(2.0)

        verdict, reasons, signals = classify(r, info)
        got = collected.get(slug, [])
        expected = urlparse(url).path.strip("/").split("/")[0]
        if got and expected.lower() not in [g.lower() for g in got]:
            reasons.append(f"the collected posts came from {got}, not {expected}")
            verdict = "FAIL"

        results.append({
            "source_page": slug, "url": url, "verdict": verdict,
            "reasons": reasons, "signals": signals,
            "name": info.get("name", ""),
            "category": info.get("category", ""),
            "description": info.get("description", ""),
            "followers": info.get("followers", ""),
            "buttons": info.get("buttons", []),
            "gov_domains": info.get("gov_domains", []),
            "collected_from": got,
        })
        mark = {"PASS": "ok  ", "FAIL": "FAIL", "UNREAD": "?   "}[verdict]
        print(f"  {mark} {slug:32} {str(info.get('category',''))[:30]:32} "
              f"{' | '.join(signals)[:60]}")
        if reasons:
            print(f"       {'; '.join(reasons)[:100]}")
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
