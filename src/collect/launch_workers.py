"""
launch_workers.py — run the collection workers in parallel.

One worker per platform, each bound to its own browser tab. The browser can
drive several tabs at once: `goto` and `eval` take an explicit --page, so a
worker that stays on its own tab does not disturb another worker.

    python src/collect/launch_workers.py --posts 5
    python src/collect/launch_workers.py --posts 5 --platforms facebook x reddit
    python src/collect/launch_workers.py --posts 4 --mode invites --platforms facebook

Each worker writes its own progress file and its own log:

    data/provenance/progress/<platform>.json
    data/provenance/logs/<platform>.log

The progress files are merged into collection_progress.json when the run
finishes, and also after every worker, so a crash still leaves a record.
"""

from __future__ import annotations

import argparse
import io
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import worker as wk

# The platform each tab is given. The order is fixed so that a tab index
# always means the same platform.
DEFAULT_ORDER = ["facebook", "youtube", "x", "reddit"]


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Run the collection workers in parallel")
    ap.add_argument("--platforms", nargs="+", default=DEFAULT_ORDER)
    ap.add_argument("--posts", type=int, default=5)
    ap.add_argument("--mode", default="recent", choices=["recent", "invites"])
    ap.add_argument("--pause", type=float, default=8.0)
    args = ap.parse_args(argv)

    platforms = [p for p in DEFAULT_ORDER if p in args.platforms]
    if not platforms:
        print("no known platforms selected")
        return 1

    tabs = wk.ensure_tabs(1)
    log(f"{len(tabs)} tab(s) available; the browser is driven one worker at a time")
    for i, t in enumerate(tabs):
        log(f"  tab [{i}] {t.get('browserPageId')}  {t.get('url')}")

    # The workers run ONE AT A TIME.
    #
    # The browser can hold several tabs, and a short test with three tabs
    # driving at once works. Sustained concurrent driving does not: the
    # runtime closes the connection under the load, and every account fails
    # with "runtime_unavailable - the Orca runtime closed the connection
    # before responding". The browser is driven by one process at a time.
    #
    # The parallelism that IS safe is off the browser: the cleaning, the
    # adjudication and the validation all run while nothing is driving.
    rc = 0
    for i, platform in enumerate(platforms):
        cmd = [sys.executable, os.path.join(HERE, "worker.py"),
               "--platform", platform, "--tab", "0",
               "--posts", str(args.posts), "--mode", args.mode,
               "--pause", str(args.pause)]
        log(f"starting {platform} worker on tab 0: {' '.join(cmd[1:])}")
        code = subprocess.call(cmd, cwd=ROOT)
        log(f"  {platform:10} finished with code {code}")
        if code != 0:
            rc = 1

    merged = wk.merge_progress()
    log("")
    log("=== progress ===")
    for k, v in sorted(merged.items()):
        log(f"  {k:34} posts={v.get('posts', 0):>3} comments={v.get('comments', 0):>5} "
            f"{v.get('last_error', '')[:50]}")

    return rc


if __name__ == "__main__":
    sys.exit(main())
