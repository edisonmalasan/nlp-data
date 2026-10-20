"""
collect_all.py — run the whole collection, one platform at a time.

    python src/collect/collect_all.py --posts 12

The Orca browser allows one driven tab at a time, so the platforms have to
run in sequence, not in parallel. This script does that: Facebook, then the
official accounts discovered from the agencies' own pages, then YouTube, X
and Reddit, and finally the conversion into the interim layer and the
cleaning pass.

Every stage is resumable. An account that already has a raw snapshot is
skipped, so re-running this after an interruption continues where it
stopped rather than starting over.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import orca_browser as ob
import run_all
import discover_links

INTERIM = os.path.join(ROOT, "data", "interim")
PROCESSED = os.path.join(ROOT, "data", "processed")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sh(*args):
    """Run a repo script."""
    r = subprocess.run([sys.executable] + list(args), cwd=ROOT,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    out = (r.stdout or "") + (r.stderr or "")
    for line in out.splitlines():
        if line.strip():
            log("    " + line)
    return r.returncode


def convert_and_clean():
    """Raw snapshots -> interim -> cleaned pool."""
    log("converting the raw snapshots to the interim layer")
    registry = run_all.read_registry()
    seen = set()
    for r in registry:
        key = (r["platform"], r["source_page"])
        if key in seen:
            continue
        seen.add(key)
        d = os.path.join(ROOT, "data", "raw", r["platform"], r["source_page"])
        if not os.path.isdir(d):
            continue
        sh(os.path.join("src", "collect", "to_interim.py"),
           "--snapshot-dir", d,
           "--source-page", r["source_page"],
           "--platform", r["platform"],
           "--agency-id", r["agency_id"],
           "--source-page-name", r.get("source_page_name", ""),
           "--append")

    log("cleaning")
    pool = os.path.join(INTERIM, "comments_captured.csv")
    if not os.path.exists(pool):
        log("no interim file - nothing to clean")
        return 1
    return sh(os.path.join("src", "clean", "pipeline.py"),
              "--pool", pool,
              "--out", os.path.join(PROCESSED, "candidate_pool.csv"),
              "--ledger-out", os.path.join(INTERIM, "exclusion_ledger.csv"),
              "--report", os.path.join(INTERIM, "cleaning_report.json"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run the whole collection")
    ap.add_argument("--posts", type=int, default=12,
                    help="posts per Facebook account")
    ap.add_argument("--skip-links", action="store_true",
                    help="do not discover the other official accounts")
    ap.add_argument("--only", default=None,
                    help="run just this platform, e.g. youtube")
    ap.add_argument("--mode", default="recent", choices=["recent", "invites"],
                    help="recent = the most recent posts; "
                         "invites = the posts that invite a citizen request")
    args = ap.parse_args(argv)

    platforms = ["facebook", "youtube", "x", "reddit"]
    if args.only:
        platforms = [args.only]

    for platform in platforms:
        log(f"=== {platform.upper()} ===")
        rc = run_all.main(["--platform", platform,
                           "--posts", str(args.posts),
                           "--mode", args.mode,
                           "--notes", f"collection run via orca built-in browser, "
                                     f"{args.posts} posts/account"])
        if rc != 0:
            log(f"  {platform} finished with code {rc}")

    if not args.skip_links and "facebook" in platforms:
        log("=== discovering the other official accounts ===")
        try:
            discover_links.main(["--apply"])
        except Exception as e:
            log(f"  link discovery failed: {e}")

    if not args.only:
        convert_and_clean()

    log("=== progress ===")
    run_all.main(["--status"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
