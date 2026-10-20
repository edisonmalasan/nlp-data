"""
to_interim.py — Stage 1b. Turn a raw capture into the pipeline's input.

The collection method for this project is a computer-use agent driving the
researcher's own Chrome, already signed in to Facebook, X, YouTube and Reddit.
That agent reads the rendered DOM and writes a raw snapshot.

This script is the hand-off point. It takes the raw snapshot, checks it, and
writes the two interim files the cleaning pipeline consumes:

    data/interim/comments_captured.csv
    data/interim/posts_captured.csv

Nothing is filtered here. The interim layer is verbatim, so the cleaning
stage can be re-run from it without re-scraping.

Usage
-----
    python src/collect/to_interim.py \\
        --snapshot data/raw/facebook/dost_pagasa/fb_dost_pagasa_2026-10-20T09-30.json \\
        --source-page dost_pagasa \\
        --platform facebook \\
        --outdir data/interim

    # several snapshots at once
    python src/collect/to_interim.py \\
        --snapshot-dir data/raw/facebook --source-page dost_pagasa --platform facebook

The raw snapshot format is documented in docs/COLLECTION_PROTOCOL.md.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from alt_text import clean_comment
LOG_PATH = os.path.join(ROOT, "data", "provenance", "collection_log.csv")

COMMENT_FIELDS = [
    "comment_id", "platform", "source_page", "source_page_name", "agency_id",
    "post_id", "post_url", "post_date", "post_text", "post_media_type",
    "is_reply", "parent_comment_id", "parent_comment_text", "comment_text",
    "author_name", "author_is_official", "timestamp_raw", "source_snapshot",
    "collected_at",
]

POST_FIELDS = [
    "post_id", "platform", "source_page", "source_page_name", "agency_id",
    "post_url", "post_date", "post_text", "post_media_type", "post_topic",
    "source_snapshot", "collected_at",
]

LOG_FIELDS = ["run_id", "platform", "source_page", "collection_method", "tool",
               "version", "user_agent", "delay_seconds", "post_ids_collected",
               "comments_collected", "collected_at", "raw_snapshot_id", "notes"]

# Handles that are agency accounts rather than citizens
OFFICIAL_MARKERS = ["dost", "pagasa", "dswd", "deped", "doh", "dpwh", "dilg",
                     "ndrrmc", "bfp", "dti", "denr", "gov.ph", "official",
                     "philippines", "hugass", "sec.", "secretary", "office of"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# The contract fixes the comment_id pattern as <platform>_<source_page>_<seq4>.
# The platform part is the short prefix, not the full platform name.
PLATFORM_PREFIX = {
    "facebook": "fb",
    "youtube": "yt",
    "reddit": "rd",
    "x": "x",
}


def platform_prefix(platform: str) -> str:
    return PLATFORM_PREFIX.get((platform or "").lower(), (platform or "x").lower()[:2])


def slugify(text: str) -> str:
    out = "".join(ch if ch.isalnum() else "_" for ch in (text or "").lower())
    while "__" in out:
        out = out.replace("__", "_")
    return out.strip("_")


def make_post_id(platform: str, source_page: str, post_url: str, given: str = "") -> str:
    if given:
        return given
    h = hashlib.sha1((post_url or "").encode("utf-8")).hexdigest()[:16]
    return f"{platform_prefix(platform)}_{slugify(source_page)}_{h}"


def make_comment_id(platform: str, source_page: str, seq: int) -> str:
    return f"{platform_prefix(platform)}_{slugify(source_page)}_{seq:04d}"


def looks_official(author_name: str) -> bool:
    """Is the commenter the agency itself rather than a citizen?"""
    low = (author_name or "").lower()
    if not low:
        return False
    return any(m in low for m in OFFICIAL_MARKERS)


def load_snapshot(path: str) -> dict:
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh)


def validate(snap: dict, path: str) -> list:
    """Return a list of problems. An empty list means the snapshot is usable."""
    problems = []
    if not isinstance(snap, dict):
        return [f"{path}: top level is not an object"]
    posts = snap.get("posts")
    if not isinstance(posts, list):
        return [f"{path}: missing a 'posts' list"]
    if not posts:
        return [f"{path}: 'posts' is empty"]
    for i, p in enumerate(posts):
        if not isinstance(p, dict):
            problems.append(f"{path}: post {i} is not an object")
            continue
        comments = p.get("comments")
        if not isinstance(comments, list):
            problems.append(f"{path}: post {i} has no 'comments' list")
            continue
        for j, c in enumerate(comments):
            if not isinstance(c, dict):
                problems.append(f"{path}: post {i} comment {j} is not an object")
    return problems


def flatten(snap: dict, path: str, source_page: str, platform: str,
            agency_id: str = "", source_page_name: str = "",
            start_seq: int = 0) -> tuple:
    """Return (comment_rows, post_rows).

    `start_seq` continues the comment sequence from where a previous snapshot
    left off. The sequence is GLOBAL for a (platform, source_page) pair, not
    per post: comment_id must be unique across the whole dataset, and the
    contract fixes it as <platform>_<source_page>_<seq4>.
    """
    run_id = snap.get("run_id") or os.path.splitext(os.path.basename(path))[0]
    collected_at = snap.get("collected_at") or now_iso()
    snap_id = snap.get("raw_snapshot_id") or run_id

    # the sampling stratum this snapshot was collected under: stratum A is the
    # most recent posts, stratum B is the posts that invite a citizen request
    stratum = "invites" if "stratum=invites" in (snap.get("notes") or "") else "recent"

    comment_rows = []
    post_rows = []
    seq = start_seq

    for p in snap.get("posts", []):
        post_url = p.get("post_url", "")
        post_id = make_post_id(platform, source_page, post_url, p.get("post_id", ""))

        post_rows.append({
            "post_id": post_id,
            "platform": platform,
            "source_page": source_page,
            "source_page_name": source_page_name,
            "agency_id": agency_id,
            "post_url": post_url,
            "post_date": p.get("post_date", ""),
            "post_text": p.get("post_text", ""),
            "post_media_type": p.get("post_media_type", "unknown"),
            "post_topic": p.get("post_topic", ""),
            "source_snapshot": snap_id,
            "collected_at": collected_at,
        })

        parent_ids = {}
        for c in p.get("comments", []):
            text = clean_comment(c.get("comment_text") or "")
            if not text:
                continue
            seq += 1
            cid = make_comment_id(platform, source_page, seq)

            parent_text = (c.get("parent_comment_text") or "").strip()
            parent_id = ""
            if parent_text:
                parent_id = parent_ids.get(parent_text, "")
                if not parent_id:
                    parent_id = f"{cid}_p"
                parent_ids[parent_text] = parent_id

            author = c.get("author_name", "")
            comment_rows.append({
                "comment_id": cid,
                "platform": platform,
                "source_page": source_page,
                "source_page_name": source_page_name,
                "agency_id": agency_id,
                "post_id": post_id,
                "post_url": post_url,
                "post_date": p.get("post_date", ""),
                "post_text": p.get("post_text", ""),
                "post_media_type": p.get("post_media_type", "unknown"),
                "is_reply": "true" if c.get("is_reply") or parent_text else "false",
                "parent_comment_id": parent_id,
                "parent_comment_text": parent_text,
                "comment_text": text,
                "author_name": author,
                "author_is_official": "true" if looks_official(author) else "false",
                "timestamp_raw": c.get("timestamp_raw", ""),
                "source_snapshot": snap_id,
                "collected_at": collected_at,
                "stratum": stratum,
            })

    return comment_rows, post_rows


def next_seq(existing_csv: str, platform: str, source_page: str) -> int:
    """The highest comment sequence already used for this (platform, source_page).

    Continuing from here is what keeps comment_id unique when several
    snapshots of the same account are converted in separate runs.
    """
    if not os.path.exists(existing_csv):
        return 0
    prefix = f"{platform_prefix(platform)}_{slugify(source_page)}_"
    highest = 0
    with io.open(existing_csv, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            cid = row.get("comment_id", "")
            if cid.startswith(prefix):
                tail = cid[len(prefix):]
                if tail.isdigit():
                    highest = max(highest, int(tail))
    return highest


def write_csv(path: str, rows: list, fields: list, append: bool = False) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    exists = os.path.exists(path) and append
    with io.open(path, "a" if append else "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        if not exists:
            w.writeheader()
        for r in rows:
            w.writerow(r)


def append_log(row: dict) -> None:
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    new = not os.path.exists(LOG_PATH)
    with io.open(LOG_PATH, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=LOG_FIELDS, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow({f: row.get(f, "") for f in LOG_FIELDS})


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Stage 1b - raw capture to interim CSV")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--snapshot", help="one raw snapshot JSON")
    g.add_argument("--snapshot-dir", help="a directory of raw snapshot JSONs")
    ap.add_argument("--source-page", required=True)
    ap.add_argument("--platform", required=True,
                    choices=["facebook", "youtube", "reddit", "x"])
    ap.add_argument("--outdir", default=os.path.join(ROOT, "data", "interim"))
    ap.add_argument("--agency-id", default="")
    ap.add_argument("--source-page-name", default="")
    ap.add_argument("--append", action="store_true",
                    help="append to the existing interim files instead of replacing them")
    args = ap.parse_args(argv)

    paths = []
    if args.snapshot:
        paths = [args.snapshot]
    else:
        for dp, _dn, fn in os.walk(args.snapshot_dir):
            for f in sorted(fn):
                if f.endswith(".json"):
                    paths.append(os.path.join(dp, f))
    if not paths:
        print("No snapshots found.")
        return 1

    # A snapshot directory can hold several accounts. Only the ones for this
    # source page belong here, otherwise the same capture is converted twice.
    scoped = []
    for path in paths:
        try:
            head = json.load(io.open(path, encoding="utf-8"))
        except Exception:
            scoped.append(path)
            continue
        if head.get("source_page", "") in ("", args.source_page):
            scoped.append(path)
    skipped = len(paths) - len(scoped)
    paths = scoped

    all_comments = []
    all_posts = []
    problems = []
    used_ids = set()

    cpath = os.path.join(args.outdir, "comments_captured.csv")
    seq = next_seq(cpath, args.platform, args.source_page)

    for path in paths:
        try:
            snap = load_snapshot(path)
        except Exception as e:
            problems.append(f"{path}: unreadable ({e})")
            continue

        probs = validate(snap, os.path.basename(path))
        if probs:
            problems.extend(probs)
            continue

        c_rows, p_rows = flatten(snap, path, args.source_page, args.platform,
                                 args.agency_id, args.source_page_name, start_seq=seq)
        seq += len(c_rows)

        dupes = []
        for r in c_rows:
            if r["comment_id"] in used_ids:
                dupes.append(r["comment_id"])
            used_ids.add(r["comment_id"])
        if dupes:
            problems.append(f"{path}: duplicate comment_id {dupes[0]}")
            continue

        all_comments.extend(c_rows)
        all_posts.extend(p_rows)

        run_id = snap.get("run_id") or os.path.splitext(os.path.basename(path))[0]
        append_log({
            "run_id": run_id,
            "platform": args.platform,
            "source_page": args.source_page,
            "collection_method": snap.get("collection_method", "browser_dom_session"),
            "tool": snap.get("tool", "orca-computer-use"),
            "version": snap.get("tool_version", ""),
            "user_agent": snap.get("user_agent", ""),
            "delay_seconds": snap.get("delay_seconds", ""),
            "post_ids_collected": len(p_rows),
            "comments_collected": len(c_rows),
            "collected_at": snap.get("collected_at") or now_iso(),
            "raw_snapshot_id": run_id,
            "notes": snap.get("notes", ""),
        })

    if problems:
        print("PROBLEMS:")
        for p in problems[:20]:
            print(f"  - {p}")
        if len(problems) > 20:
            print(f"  ... and {len(problems) - 20} more")
        print("\nNothing was written. Fix the snapshots and run again.")

    ppath = os.path.join(args.outdir, "posts_captured.csv")
    if problems:
        # A malformed capture must not half-overwrite the interim layer.
        print("\nNothing was written. Fix the captures and run again.")
        return 1

    write_csv(cpath, all_comments, COMMENT_FIELDS, append=args.append)
    write_csv(ppath, all_posts, POST_FIELDS, append=args.append)

    print(f"\nsnapshots read : {len(paths)}")
    print(f"posts          : {len(all_posts)}")
    print(f"comments       : {len(all_comments)}")
    print(f"-> {cpath}")
    print(f"-> {ppath}")
    print(f"logged -> {LOG_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
