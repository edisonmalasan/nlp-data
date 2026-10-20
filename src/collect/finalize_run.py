"""
finalize_run.py — the remaining sequence, end to end.

    python src/collect/finalize_run.py

1. verify the candidate source accounts and add the good ones to the registry
2. collect Facebook, the primary platform, from every account
3. collect YouTube
4. collect X
5. collect the request-inviting stratum on Facebook
6. rebuild the interim layer, clean it, and print the report

Every stage is resumable, so the run can be interrupted and started again.
Facebook runs first because it is the primary dataset.
"""

from __future__ import annotations

import io
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import collect_all
import run_all
import verify_sources
import discover_from_websites


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def step(name, fn):
    log(f"=== {name} ===")
    try:
        fn()
    except Exception as e:
        log(f"  {name} failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
    log("")


def main() -> int:
    posts = int(os.environ.get("POSTS", "8"))

    # The agency's own website linking its Facebook page is the strongest
    # evidence available, and the page name is then checked against the
    # agency. Guessing slugs does not work - "PSAofficial" is a page called
    # "Pet Society".
    step("finding the official pages from the agency websites",
         lambda: discover_from_websites.main(["--apply"]))

    for platform in ("facebook", "youtube", "x"):
        step(f"collecting {platform}", lambda p=platform: run_all.main(
            ["--platform", p, "--posts", str(posts),
             "--notes", f"collection run via orca built-in browser, {posts} posts/account"]))

    step("collecting the request-inviting stratum (facebook)",
         lambda: run_all.main(
             ["--platform", "facebook", "--posts", str(posts), "--mode", "invites",
              "--notes", f"collection run via orca built-in browser, {posts} posts/account, "
                        f"stratum=invites"]))

    step("rebuilding the interim layer and cleaning",
         collect_all.convert_and_clean)

    log("=== the dataset report ===")
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "dataset_report.py"),
                        "--json", os.path.join(ROOT, "data", "provenance", "dataset_report.json")],
                       cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    print(r.stdout)
    if r.stderr:
        print(r.stderr)

    log("=== progress ===")
    run_all.main(["--status"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
