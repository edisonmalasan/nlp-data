"""
recover_captions.py — fill in the missing post captions.

A post's caption is read from the message container, which Facebook marks
with data-ad-comet-preview. The extractor that used to read the caption had
a defect - it took the first piece of text in the post's article, which was
sometimes a comment - and 56 of the 92 captured posts ended up with no
caption at all.

This re-opens only the posts that are missing a caption and reads it with
the corrected rule. It does not touch the comments, the labels or the
splits: the caption is post context, and the contract's V-07 check compares
the dataset's denormalised post fields against the post master, so both
are written together.

    python src/collect/recover_captions.py
    python src/collect/recover_captions.py --apply
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

DATASET = os.path.join(ROOT, "data", "processed", "dataset_full.csv")
EXT = os.path.join(ROOT, "data", "processed", "dataset_v1_ext.csv")
PRIMARY = os.path.join(ROOT, "data", "processed", "dataset_v1.csv")
POSTS = os.path.join(ROOT, "data", "processed", "posts_v1.csv")
MAP_PATH = os.path.join(ROOT, "data", "provenance", "recovered_captions.json")

# The caption is the message container. The fallback is the first piece of
# text in the post's own article that is not a comment and does not contain
# one - the rule the extractor was corrected to use.
CAPTION_JS = r"""
(() => {
  const clean = s => (s || '').replace(/\u00a0/g, ' ').replace(/[ \t]+/g, ' ').trim();
  const COMMENT_SEL = 'div[role="article"][aria-label^="Comment by"]';

  const arts = Array.from(document.querySelectorAll('div[role="article"]'));
  const posts = arts.filter(a =>
    !/^Comment by/.test(a.getAttribute('aria-label') || '') &&
    !a.closest(COMMENT_SEL));

  for (const p of posts) {
    const msg = p.querySelector('[data-ad-comet-preview]');
    if (msg) {
      const t = clean(msg.innerText);
      if (t) return JSON.stringify({text: t, how: 'message_container'});
    }
  }
  for (const p of posts) {
    if (p.querySelector(COMMENT_SEL)) continue;
    const parts = Array.from(p.querySelectorAll('div[dir="auto"]'))
      .filter(x => !x.closest(COMMENT_SEL))
      .map(x => clean(x.innerText)).filter(Boolean);
    if (parts.length) {
      return JSON.stringify({text: parts[0], how: 'first_text_node'});
    }
  }
  return JSON.stringify({text: '', how: 'not_found'});
})()
"""


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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Recover the missing post captions")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--tab", type=int, default=0)
    ap.add_argument("--pause", type=float, default=1.5)
    args = ap.parse_args(argv)

    rows = read_rows(EXT)
    if not rows:
        print("no dataset to work from")
        return 1

    # the posts that are missing a caption
    by_post = {}
    for r in rows:
        by_post.setdefault(r["post_id"], r)
    missing = [r for r in by_post.values()
               if not (r.get("post_text") or "").strip()]
    print(f"{len(missing)} of {len(by_post)} posts have no caption")

    tabs = ob.list_tabs()
    while len(tabs) <= args.tab:
        ob.orca("tab", "create")
        time.sleep(1.5)
        tabs = ob.list_tabs()
    page = ob.pick_tab(tabs, index=args.tab)["browserPageId"]

    recovered = {}
    if os.path.exists(MAP_PATH):
        try:
            recovered = json.load(io.open(MAP_PATH, encoding="utf-8"))
        except Exception:
            recovered = {}

    # The account page of each post, so the permalink can be clicked there.
    #
    # The URL has to come from the source REGISTRY, never from the slug:
    # source_page is a short label used in the comment_id ("deped"), and
    # facebook.com/deped is NOT the Department of Education's page - its
    # page is facebook.com/DepartmentOfEducation.PH. Building the URL from
    # the slug would open an unrelated page.
    registry = {}
    reg_path = os.path.join(ROOT, "data", "provenance", "government_agencies.csv")
    if os.path.exists(reg_path):
        with io.open(reg_path, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                if r.get("platform") == "facebook":
                    registry[r["source_page"]] = r.get("official_account_url", "")

    account_of = {}
    for r in missing:
        url = registry.get(r["source_page"], "")
        if not url:
            print(f"  no registry URL for {r['source_page']}, skipping")
            continue
        account_of.setdefault(r["source_page"], url)

    current_account = None
    for i, r in enumerate(missing, 1):
        pid = r["post_id"]
        if pid in recovered and recovered[pid].get("text"):
            continue
        url = r["post_url"]
        account = account_of.get(r["source_page"], "")
        try:
            # A direct navigation to a post permalink does not render the post
            # for a logged-in session - the browser serves the home feed. The
            # permalink has to be clicked on the account's own page.
            if account != current_account:
                ob.goto(page, account, settle=6.0)
                ob.wait_for_content(page, ["followers", "Posts"], timeout=20.0)
                ob.open_posts_tab(page, "facebook")
                time.sleep(2.0)
                current_account = account
            state = ob.click_permalink(page, url, rounds=8)
            if state != "clicked":
                recovered[pid] = {"text": "", "how": "not_clicked", "post_url": url}
                print(f"  [{i}/{len(missing)}] {pid[:16]} the permalink was not on the page")
                continue
            time.sleep(2.0)
            info = ob.eval_json(page, CAPTION_JS) or {}
        except ob.OrcaError as e:
            print(f"  [{i}/{len(missing)}] {pid[:16]} failed: {e}")
            continue
        text = (info.get("text") or "").strip()
        how = info.get("how", "")
        if text:
            recovered[pid] = {"text": text, "how": how, "post_url": url}
            print(f"  [{i}/{len(missing)}] {pid[:16]} recovered ({how}) {text[:64]!r}")
        else:
            recovered[pid] = {"text": "", "how": how, "post_url": url}
            print(f"  [{i}/{len(missing)}] {pid[:16]} still empty")
        with io.open(MAP_PATH, "w", encoding="utf-8", newline="") as fh:
            json.dump(recovered, fh, indent=2, ensure_ascii=False)
        time.sleep(args.pause)

    n_ok = sum(1 for v in recovered.values() if v.get("text"))
    print(f"\n{n_ok} of {len(recovered)} posts have a caption")
    if not args.apply:
        print("(re-run with --apply to write them into the dataset)")
        return 0

    # write the caption into every row of that post, in all three files
    for path in (EXT, PRIMARY, os.path.join(ROOT, "data", "processed", "dataset_full.csv")):
        rs = read_rows(path)
        if not rs:
            continue
        changed = 0
        for r in rs:
            cap = recovered.get(r["post_id"], {}).get("text")
            if cap and not (r.get("post_text") or "").strip():
                r["post_text"] = cap
                changed += 1
        if changed:
            write_rows(path, rs, list(rs[0].keys()))
        print(f"  {os.path.basename(path):24} {changed} row(s) updated")

    # the post master
    prs = read_rows(POSTS)
    if prs:
        changed = 0
        for r in prs:
            cap = recovered.get(r["post_id"], {}).get("text")
            if cap and not (r.get("post_text") or "").strip():
                r["post_text"] = cap
                changed += 1
        if changed:
            write_rows(POSTS, prs, list(prs[0].keys()))
        print(f"  {os.path.basename(POSTS):24} {changed} row(s) updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
