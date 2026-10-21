"""
pending_adjudication.py — the rows that still need a decision.

After the collector adds rows, the review batches grow. This works out
which rows have no decision yet and writes them out as one file, so the
adjudication pass is a single clean job rather than a diff by hand.

    python tools/pending_adjudication.py
    python tools/pending_adjudication.py --out data/interim/pending_rows.jsonl
"""

from __future__ import annotations

import argparse
import glob
import io
import json
import os
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATCHES = os.path.join(ROOT, "data", "interim", "review_batches")
DECISIONS = os.path.join(ROOT, "data", "interim", "decisions")
OUT = os.path.join(ROOT, "data", "interim", "pending_rows.jsonl")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="List the rows that need a decision")
    ap.add_argument("--out", default=OUT)
    args = ap.parse_args(argv)

    needed = []
    for f in sorted(glob.glob(os.path.join(BATCHES, "batch_*.jsonl"))):
        with io.open(f, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    needed.append(json.loads(line))

    decided = set()
    for f in sorted(glob.glob(os.path.join(DECISIONS, "*.jsonl"))):
        with io.open(f, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    try:
                        decided.add(json.loads(line)["comment_id"])
                    except Exception:
                        pass

    pending = [r for r in needed if r["comment_id"] not in decided]
    with io.open(args.out, "w", encoding="utf-8", newline="") as fh:
        for r in pending:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"rows needing a decision : {len(needed)}")
    print(f"already decided          : {len(needed) - len(pending)}")
    print(f"PENDING                  : {len(pending)}  -> {args.out}")
    if pending:
        print(f"  uncertain : {sum(1 for r in pending if r.get('review_kind') == 'uncertain')}")
        print(f"  audit     : {sum(1 for r in pending if r.get('review_kind') == 'audit')}")
        print(f"  by rule   : {dict(Counter(r.get('heuristic_rule', '') for r in pending))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
