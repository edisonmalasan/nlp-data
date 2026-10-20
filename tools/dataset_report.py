"""
dataset_report.py — the numbers for the write-up.

Prints the dataset's composition, the class balance, the per-agency and
per-post distribution, the sampling strata, and the quality checks. This is
the source for the figures in the Methodology and Results sections.

    python tools/dataset_report.py
    python tools/dataset_report.py --pool data/processed/candidate_pool.csv
    python tools/dataset_report.py --json data/provenance/dataset_report.json
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# A request marker is a hint, not the label. It is used here only to show
# what the corpus looks like before it is labelled. The label itself comes
# from the annotator.
REQUEST_MARKER = re.compile(
    r"\b(please|dapat|kailangan|sana|paki|ayusin|linisin|palitan|ibigay|bigyan|"
    r"ipagbigay|paano po|how (do|can|to)|pls|fix|release|provide|isumbong|"
    r"humiling|ipagpaalam)\b", re.I)


def load(path):
    with io.open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def pct(n, d):
    return f"{n/d:.0%}" if d else "0%"


def report(pool_path: str, ledger_path: str = None):
    rows = load(pool_path)
    print("=" * 72)
    print("DATASET REPORT")
    print("=" * 72)
    print(f"pool: {pool_path}")
    print(f"usable comments: {len(rows)}")
    if not rows:
        return {}

    posts = {r["post_id"] for r in rows}
    agencies = Counter(r.get("agency_id") or r.get("source_page") for r in rows)
    platforms = Counter(r.get("platform", "") for r in rows)
    strata = Counter(r.get("stratum", "recent") for r in rows)

    print(f"distinct posts   : {len(posts)}")
    print(f"agencies         : {len(agencies)}")
    print(f"platforms        : {dict(platforms)}")
    print(f"strata           : {dict(strata)}")

    # ---- per post distribution --------------------------------------------
    per_post = Counter(r["post_id"] for r in rows)
    ordered = per_post.most_common()
    top8 = sum(n for _, n in ordered[:8])
    print(f"\ntop 8 posts hold : {top8} of {len(rows)} ({pct(top8, len(rows))})")
    print(f"median per post  : {sorted(per_post.values())[len(per_post)//2]}")
    print(f"posts with < 10  : {sum(1 for _, n in per_post.items() if n < 10)}")

    # ---- per agency --------------------------------------------------------
    print("\nper agency")
    print(f"  {'agency':22} {'rows':>6} {'posts':>6} {'req%':>6}")
    for a, n in agencies.most_common():
        sub = [r for r in rows if (r.get("agency_id") or r.get("source_page")) == a]
        p = len({r["post_id"] for r in sub})
        req = sum(1 for r in sub if REQUEST_MARKER.search(r.get("comment_text_norm", "")))
        print(f"  {str(a):22} {n:>6} {p:>6} {pct(req, n):>6}")

    # ---- request marker rate ----------------------------------------------
    req = sum(1 for r in rows if REQUEST_MARKER.search(r.get("comment_text_norm", "")))
    print(f"\nrequest-marker rate : {req}/{len(rows)} = {pct(req, len(rows))}")
    print("  (an upper bound on the actionable rate; the label itself comes from the annotator)")

    # ---- stratum balance ---------------------------------------------------
    for s, n in strata.most_common():
        sub = [r for r in rows if r.get("stratum", "recent") == s]
        rq = sum(1 for r in sub if REQUEST_MARKER.search(r.get("comment_text_norm", "")))
        print(f"  stratum {s:10} {n:>6} comments, request-marker {pct(rq, n)}")

    # ---- text ------------------------------------------------------------
    lens = sorted(len(r.get("comment_text_norm", "")) for r in rows)
    print(f"\ncomment length   : median {lens[len(lens)//2]}, "
          f"p90 {lens[int(len(lens)*0.9)]}, max {lens[-1]}")
    print(f"empty text       : {sum(1 for r in rows if not r.get('comment_text_norm','').strip())}")

    # ---- post context ------------------------------------------------------
    missing_ctx = sum(1 for r in rows if not r.get("post_text", "").strip())
    print(f"missing post ctx : {missing_ctx} ({pct(missing_ctx, len(rows))})")

    # ---- labels ------------------------------------------------------------
    labelled = [r for r in rows if r.get("label") in ("0", "1")]
    if labelled:
        c = Counter(r["label"] for r in labelled)
        print(f"\nlabelled         : {len(labelled)}")
        print(f"  actionable (1) : {c.get('1', 0)} ({pct(c.get('1',0), len(labelled))})")
        print(f"  other (0)      : {c.get('0', 0)} ({pct(c.get('0',0), len(labelled))})")

    # ---- exclusion ledger --------------------------------------------------
    if ledger_path and os.path.exists(ledger_path):
        led = load(ledger_path)
        print(f"\nexclusions       : {len(led)}")
        for reason, n in Counter(r.get("_reason", "") for r in led).most_common():
            print(f"  {reason:16} {n}")

    return {
        "n_usable": len(rows),
        "n_posts": len(posts),
        "n_agencies": len(agencies),
        "platforms": dict(platforms),
        "strata": dict(strata),
        "per_agency": dict(agencies),
        "top8_share": round(top8 / len(rows), 4),
        "request_marker_rate": round(req / len(rows), 4),
        "median_comment_length": lens[len(lens) // 2],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Dataset statistics for the write-up")
    ap.add_argument("--pool", default=os.path.join(ROOT, "data", "processed", "candidate_pool.csv"))
    ap.add_argument("--ledger", default=os.path.join(ROOT, "data", "interim", "exclusion_ledger.csv"))
    ap.add_argument("--json", default=None, help="also write the summary as JSON")
    args = ap.parse_args(argv)

    stats = report(args.pool, args.ledger)
    if args.json and stats:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        io.open(args.json, "w", encoding="utf-8", newline="").write(
            json.dumps(stats, indent=2, ensure_ascii=False))
        print(f"\nsummary -> {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
