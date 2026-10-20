"""
run_all.py — collect every registered source, one account at a time.

Reads the source registry, drives Orca's built-in browser for each account, and
writes one raw snapshot per account. Resumable: an account that already has a
snapshot is skipped, so the run can be stopped and restarted without losing
work or double-counting.

    python src/collect/run_all.py --platform facebook --posts 12
    python src/collect/run_all.py --platform youtube --posts 8
    python src/collect/run_all.py --status

Each platform uses its own tab in the browser, so a run never navigates away
from a tab another platform needs.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import orca_browser as ob

REGISTRY = os.path.join(ROOT, "data", "provenance", "government_agencies.csv")
RAW = os.path.join(ROOT, "data", "raw")
PROGRESS = os.path.join(ROOT, "data", "provenance", "collection_progress.json")

# Which browser tab each platform uses.
#
# The browser drives ONE tab at a time, and a tab only renders when it is the
# one being driven - a YouTube tab left in the background has an empty body.
# So every platform is collected in the SAME tab, which is navigated to the
# platform it needs. The other tabs are left alone.
PLATFORM_TAB = {"facebook": 0, "youtube": 0, "x": 0, "reddit": 0}

# The extractor for each platform.
EXTRACTORS = {
    "facebook": "extract_facebook.js",
    "youtube": "extract_youtube.js",
    "x": "extract_x.js",
    "reddit": "extract_reddit.js",
}

# How the account page is reached for each platform.
ACCOUNT_URL = {
    "facebook": lambda r: r["official_account_url"],
    "youtube": lambda r: r["official_account_url"],
    "x": lambda r: r["official_account_url"],
    "reddit": lambda r: r["official_account_url"],
}


def read_registry():
    with io.open(REGISTRY, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def load_progress():
    if os.path.exists(PROGRESS):
        try:
            return json.load(io.open(PROGRESS, encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_progress(p):
    os.makedirs(os.path.dirname(PROGRESS), exist_ok=True)
    io.open(PROGRESS, "w", encoding="utf-8", newline="").write(
        json.dumps(p, indent=2))


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def existing_snapshots(platform, source_page, mode="recent"):
    """The snapshots already collected for this account and this stratum.

    The two strata share a directory, so a snapshot collected under the other
    stratum does not count: without this, collecting stratum B would make
    stratum A look already collected and it would be skipped.
    """
    d = os.path.join(RAW, platform, source_page)
    if not os.path.isdir(d):
        return []
    want_invites = (mode == "invites")
    out = []
    for f in sorted(os.listdir(d)):
        if not f.endswith(".json"):
            continue
        path = os.path.join(d, f)
        try:
            snap = json.load(io.open(path, encoding="utf-8"))
        except Exception:
            continue
        is_invites = "stratum=invites" in (snap.get("notes") or "")
        if is_invites == want_invites:
            out.append(path)
    return out


def run_one(page, row, posts, notes, mode="recent"):
    """Collect one account. Returns (n_posts, n_comments, error)."""
    platform = row["platform"]
    source_page = row["source_page"]
    url = ACCOUNT_URL[platform](row)

    ob.goto(page, url, settle=5.0)
    time.sleep(2.0)

    extract_js = ob.load_extract_js(EXTRACTORS[platform])

    if platform == "youtube":
        # the channel's videos tab is what lists the videos
        ob.goto(page, url.rstrip("/") + "/videos", settle=5.0)
        time.sleep(2.0)

    if mode == "invites" and platform == "facebook":
        urls = ob.find_inviting_posts(page, limit=posts)
    else:
        urls = ob.discover_posts(page, platform, limit=posts)
    if not urls:
        urls = [url]

    if not urls:
        return 0, 0, "no post urls discovered"

    entries = []
    for u in urls[:posts]:
        try:
            data = ob.capture_post(page, u, extract_js, platform)
        except ob.OrcaError as e:
            log(f"    post failed: {e}")
            continue
        n = data.get("n_comments", 0)
        entries.append((u, data))
        log(f"    {n:>4} comments  {u[-46:]}")

    if not entries:
        return 0, 0, "no posts captured"

    snap = ob.build_snapshot(source_page, row.get("source_page_name", ""),
                              row.get("agency_id", ""), platform, entries, notes=notes)
    path = ob.write_snapshot(snap)
    n_comments = sum(p["n_comments"] for p in snap["posts"])
    log(f"  SNAPSHOT {os.path.basename(path)}  {len(snap['posts'])} post(s), {n_comments} comment(s)")
    return len(snap["posts"]), n_comments, ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Collect every registered source")
    ap.add_argument("--platform", default="facebook",
                    choices=["facebook", "youtube", "x", "reddit"])
    ap.add_argument("--posts", type=int, default=12)
    ap.add_argument("--notes", default="")
    ap.add_argument("--mode", default="recent", choices=["recent", "invites"],
                    help="recent = the most recent posts; "
                         "invites = the posts that invite a citizen request")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--force", action="store_true",
                    help="re-collect accounts that already have a snapshot")
    args = ap.parse_args(argv)

    registry = [r for r in read_registry() if r["platform"] == args.platform]
    progress = load_progress()

    if args.status:
        for r in registry:
            k = f"{r['platform']}/{r['source_page']}"
            p = progress.get(k, {})
            snaps = (existing_snapshots(r["platform"], r["source_page"], "recent")
                     + existing_snapshots(r["platform"], r["source_page"], "invites"))
            log(f"{k:32} posts={p.get('posts', 0):>3} comments={p.get('comments', 0):>5} "
                f"snapshots={len(snaps)}")
        return 0

    tabs = ob.list_tabs()
    if not tabs:
        log("no browser tabs found. open the pages in the Orca browser first.")
        return 1
    for t in tabs:
        log(f"tab [{t.get('index')}] {t.get('url')}")

    tab_index = PLATFORM_TAB.get(args.platform, 0)
    tab = ob.pick_tab(tabs, index=tab_index)
    # a stale helper session on another tab blocks this one
    try:
        ob.orca("tab", "switch", "--index", str(tab_index))
    except ob.OrcaError:
        pass
    page = tab["browserPageId"]
    log(f"using tab [{tab_index}] {tab.get('url')}")

    notes = args.notes or f"collection run via orca built-in browser, {args.posts} posts/account"
    if args.mode and args.mode != "recent":
        notes = f"{notes} stratum={args.mode}"

    for i, row in enumerate(registry, 1):
        key = f"{row['platform']}/{row['source_page']}"
        snaps = existing_snapshots(row["platform"], row["source_page"], args.mode)
        if snaps and not args.force:
            log(f"[{i}/{len(registry)}] {key}: already collected, skipping")
            continue
        log(f"[{i}/{len(registry)}] {key}  {row.get('official_account_url','')}")
        try:
            n_posts, n_comments, err = run_one(page, row, args.posts, notes, args.mode)
        except Exception as e:
            n_posts, n_comments, err = 0, 0, f"{type(e).__name__}: {e}"
            log(f"  FAILED: {err}")
            traceback.print_exc()
        prev = progress.get(key, {})
        progress[key] = {
            "posts": prev.get("posts", 0) + n_posts,
            "comments": prev.get("comments", 0) + n_comments,
            "last_error": err,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        save_progress(progress)
        if err:
            log(f"  error: {err}")
        time.sleep(3)

    log("done")
    for k, v in progress.items():
        log(f"  {k:32} posts={v.get('posts',0):>3} comments={v.get('comments',0):>5}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
