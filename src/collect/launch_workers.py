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

    tabs = wk.ensure_tabs(len(platforms))
    log(f"{len(tabs)} tabs available")
    for i, t in enumerate(tabs[:len(platforms)]):
        log(f"  tab [{i}] {t.get('browserPageId')}  {t.get('url')}")

    # the registry must not change while the workers run: they only read it
    procs = []
    for i, platform in enumerate(platforms):
        cmd = [sys.executable, os.path.join(HERE, "worker.py"),
               "--platform", platform, "--tab", str(i),
               "--posts", str(args.posts), "--mode", args.mode,
               "--pause", str(args.pause)]
        log(f"starting {platform} worker on tab {i}: {' '.join(cmd[1:])}")
        p = subprocess.Popen(cmd, cwd=ROOT)
        procs.append((platform, p))
        time.sleep(2.0)

    log("")
    log("=== the workers are running ===")
    for platform, p in procs:
        log(f"  {platform:10} pid {p.pid:>6}   log: data/provenance/logs/{platform}.log")

    rc = 0
    for platform, p in procs:
        code = p.wait()
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
