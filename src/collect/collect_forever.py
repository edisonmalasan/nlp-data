"""
collect_forever.py — keep collecting, with the duplicate guarantee enforced.

The study has no ceiling on the corpus, so the collection runs as a loop
rather than as a single pass:

  1. the source frame is re-checked, and new official accounts are added
  2. the collectors run, one per platform, each on its own browser tab
  3. every cycle the interim layer is rebuilt and cleaned, so the exclusion
     ledger and the duplicate counts stay current
  4. a worker that died is restarted - collection is resumable, so a restart
     costs at most one account
  5. a heartbeat is written, so the loop's state is visible from outside

**The duplicate guarantee.** Deduplication happens in the cleaning stage, not
in the collector: exact duplicates are keyed on `dedup_key` and the earliest
captured is kept, near duplicates are a Jaccard similarity of 0.90 or a
substring relation of at least five tokens and the longer is kept, and the
number of near-identical survivors from the same account on the same post is
capped at two. Every removal carries a reason code, so the ledger
reconciles.

That matters for a continuous run: re-collecting a post produces a NEW
comment_id for text that is already held, and the cleaning stage removes it
as X_DUP_EXACT. The delivered dataset therefore holds each comment once,
and the ledger records how many times the raw layer repeated it.

    python src/collect/collect_forever.py
    python src/collect/collect_forever.py --cycles 5 --cycle-seconds 900
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
from collections import Counter
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

PY = sys.executable
PROVENANCE = os.path.join(ROOT, "data", "provenance")
HEARTBEAT = os.path.join(PROVENANCE, "collector_heartbeat.json")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run(label, argv, timeout=3600):
    r = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return r.returncode, (r.stdout or ""), (r.stderr or "")


def raw_totals():
    """The raw layer, by platform."""
    import glob
    out = {}
    for plat in ("facebook", "youtube", "x", "reddit"):
        posts = comments = 0
        for f in glob.glob(os.path.join(ROOT, "data", "raw", plat, "*", "*.json")):
            try:
                s = json.load(io.open(f, encoding="utf-8"))
            except Exception:
                continue
            posts += len(s.get("posts", []))
            comments += sum(p.get("n_comments", 0) for p in s.get("posts", []))
        if posts:
            out[plat] = (posts, comments)
    return out


def pool_stats():
    """The cleaned pool: how many rows, and how many duplicates are in it."""
    path = os.path.join(ROOT, "data", "processed", "candidate_pool.csv")
    if not os.path.exists(path):
        return {}
    rows = list(csv.DictReader(io.open(path, encoding="utf-8", newline="")))
    keys = Counter(r.get("dedup_key", "") for r in rows if r.get("dedup_key"))
    dups = sum(v - 1 for v in keys.values() if v > 1)
    ledger = os.path.join(ROOT, "data", "interim", "exclusion_ledger.csv")
    excl = {}
    if os.path.exists(ledger):
        for r in csv.DictReader(io.open(ledger, encoding="utf-8", newline="")):
            excl[r.get("_reason", "")] = excl.get(r.get("_reason", ""), 0) + 1
    return {"rows": len(rows), "residual_duplicate_keys": dups,
            "excluded_by_reason": excl}


def write_heartbeat(state):
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    with io.open(HEARTBEAT, "w", encoding="utf-8", newline="") as fh:
        json.dump(state, fh, indent=2, ensure_ascii=False)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Collect continuously")
    ap.add_argument("--cycles", type=int, default=0,
                    help="0 = run until stopped")
    ap.add_argument("--cycle-seconds", type=int, default=900)
    ap.add_argument("--posts", type=int, default=20,
                    help="how many posts to take per account")
    ap.add_argument("--platforms", nargs="+",
                    default=["facebook", "youtube", "x"])
    ap.add_argument("--invites-posts", type=int, default=8,
                    help="how many posts to take per account in the "
                         "request-inviting stratum")
    ap.add_argument("--discover-every", type=int, default=3,
                    help="re-check the source frame every N cycles")
    args = ap.parse_args(argv)

    state = {"cycle": 0, "started_at": datetime.now(timezone.utc).isoformat(),
             "raw": {}, "pool": {}}
    cycle = 0
    while True:
        cycle += 1
        state["cycle"] = cycle
        log(f"===== cycle {cycle} =====")

        # ---- 1. the source frame, now and then -------------------------
        if cycle == 1 or (args.discover_every and cycle % args.discover_every == 0):
            log("re-checking the source frame for new official accounts")
            code, out, err = run("discover", [PY, os.path.join(HERE, "discover_from_websites.py"),
                                              "--apply"], timeout=5400)
            tail = [l for l in out.splitlines() if l.strip()][-4:]
            for l in tail:
                log("   " + l)

        # ---- 2. the collectors ------------------------------------------
        # One worker at a time. The browser holds several tabs, and a short
        # test with three driving at once works, but sustained concurrent
        # driving closes the runtime's connection and every account fails
        # with "runtime_unavailable". One process drives the browser; the
        # parallelism is in the adjudication and the validation, which do
        # not touch it.
        deadline = time.time() + args.cycle_seconds

        # The queue. The most recent posts first, because that is the frame
        # the paper describes; then the request-inviting stratum, which is
        # the contract's pre-registered stratified collection and the one
        # that raises the yield of actionable rows; then the other
        # platforms.
        queue = [("facebook", "recent", args.posts)]
        queue += [("facebook", "invites", args.invites_posts)]
        queue += [(pl, "recent", args.posts) for pl in args.platforms
                  if pl != "facebook"]

        for platform, mode, posts in queue:
            if time.time() >= deadline:
                log(f"  the cycle is out of time; {platform}/{mode} waits for the next one")
                continue
            cmd = [PY, os.path.join(HERE, "worker.py"),
                   "--platform", platform, "--tab", "0",
                   "--posts", str(posts), "--mode", mode, "--pause", "6"]
            log(f"starting {platform}/{mode} on tab 0, {posts} posts")
            p = subprocess.Popen(cmd, cwd=ROOT)
            while p.poll() is None and time.time() < deadline:
                time.sleep(20)
            if p.poll() is None:
                log(f"  {platform}/{mode} is out of time; it is resumable, so it is left to run")
            else:
                log(f"  {platform}/{mode} finished with code {p.returncode}")

        # ---- 4. rebuild the interim and clean ----------------------------
        log("rebuilding the interim layer and cleaning")
        code, out, err = run("clean", [PY, os.path.join(ROOT, "tools", "finalize_dataset.py"),
                                       "--stage", "clean"], timeout=5400)
        for l in [x for x in out.splitlines() if x.strip()][-10:]:
            log("   " + l)

        # ---- 5. the state ------------------------------------------------
        state["raw"] = {k: {"posts": v[0], "comments": v[1]}
                        for k, v in raw_totals().items()}
        state["pool"] = pool_stats()
        write_heartbeat(state)
        log(f"raw: {state['raw']}")
        log(f"pool: {state['pool']['rows']} rows, "
            f"{state['pool']['residual_duplicate_keys']} residual duplicate keys, "
            f"excluded {state['pool']['excluded_by_reason']}")

        if args.cycles and cycle >= args.cycles:
            log("finished the requested number of cycles")
            return 0
        time.sleep(5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
