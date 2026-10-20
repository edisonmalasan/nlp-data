"""
merge_decisions.py — merge the adjudicated decisions into one file.

The adjudicators write one file per group of review batches. This merges
them into `data/interim/agent_decisions.csv`, in the order the review
batches were exported, and checks that every row that needs a decision
has exactly one.

    python tools/merge_decisions.py
    python tools/merge_decisions.py --check-only
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
INTERIM = os.path.join(ROOT, "data", "interim")
DECISIONS_DIR = os.path.join(INTERIM, "decisions")
BATCHES_DIR = os.path.join(INTERIM, "review_batches")
OUT = os.path.join(INTERIM, "agent_decisions.csv")

VALID_LANGS = {"fil", "eng", "mixed"}


def read_jsonl(path):
    rows = []
    with io.open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception as e:
                print(f"  {os.path.basename(path)}:{n} is not valid JSON: {e}")
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Merge the adjudicated decisions")
    ap.add_argument("--check-only", action="store_true")
    args = ap.parse_args(argv)

    # the review batches define what needs a decision, and in what order
    needed = []
    if os.path.isdir(BATCHES_DIR):
        for f in sorted(os.listdir(BATCHES_DIR)):
            if f.startswith("batch_") and f.endswith(".jsonl"):
                for r in read_jsonl(os.path.join(BATCHES_DIR, f)):
                    needed.append(r["comment_id"])
    print(f"review rows needing a decision : {len(needed)}")

    if not os.path.isdir(DECISIONS_DIR):
        print("no decisions directory")
        return 1

    merged = {}
    conflicts = []
    for f in sorted(os.listdir(DECISIONS_DIR)):
        if not f.endswith(".jsonl"):
            continue
        path = os.path.join(DECISIONS_DIR, f)
        rows = read_jsonl(path)
        print(f"  {f:26} {len(rows):>4} rows")
        for r in rows:
            cid = r.get("comment_id")
            if not cid:
                print(f"    a row in {f} has no comment_id")
                continue
            if cid in merged and merged[cid] != r:
                conflicts.append(cid)
            merged[cid] = r

    print(f"\ntotal decisions            : {len(merged)}")
    dupes = [c for c, n in Counter(merged).items() if n > 1]
    print(f"conflicting duplicates     : {len(set(conflicts))}")

    missing = [c for c in needed if c not in merged]
    extra = [c for c in merged if c not in set(needed)]
    print(f"needed but not decided     : {len(missing)}")
    print(f"decided but not needed     : {len(extra)}")
    for c in missing[:8]:
        print(f"    missing: {c}")

    bad_lang = [c for c, r in merged.items() if r.get("language") not in VALID_LANGS]
    bad_label = [c for c, r in merged.items() if r.get("label") not in (0, 1)]
    print(f"rows with a bad language   : {len(bad_lang)}")
    print(f"rows with a bad label      : {len(bad_label)}")

    labels = Counter(r.get("label") for r in merged.values())
    n = max(len(merged), 1)
    print(f"\nlabel 1 (actionable)       : {labels.get(1, 0)} ({labels.get(1, 0) / n:.1%})")
    print(f"label 0 (other)            : {labels.get(0, 0)} ({labels.get(0, 0) / n:.1%})")
    print(f"languages                  : {dict(Counter(r.get('language') for r in merged.values()))}")

    if missing or bad_lang or bad_label:
        print("\nNOT READY - the rows above have to be resolved before release")
        return 1

    if args.check_only:
        print("\n(check only - nothing written)")
        return 0

    # write in the order the review batches were exported
    with io.open(OUT, "w", encoding="utf-8", newline="") as fh:
        for cid in needed:
            r = merged[cid]
            fh.write(json.dumps({
                "comment_id": cid,
                "label": int(r["label"]),
                "language": r.get("language", ""),
                "note": r.get("note", ""),
                "verification": r.get("verification", "auto"),
            }, ensure_ascii=False) + "\n")
    print(f"\nwrote {len(needed)} decisions -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
