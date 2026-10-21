"""
build_language_artifact.py — assemble the complete language label file.

The `language` column is assigned against ONE written convention
(`data/interim/language_convention.md`), and the result is stored in
`data/provenance/language_labels.csv`. The annotator's apply step reads
that file, so the column survives every rebuild of the dataset instead of
being recomputed from a rule on each run.

The artifact is assembled from three sources, in this order:

  1. the re-label of the original corpus
  2. the adjudicated language of the rows added since
  3. the adjudicated language of the rows the engine decided on its own

    python tools/build_language_artifact.py
"""

from __future__ import annotations

import argparse
import csv
import glob
import io
import json
import os
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACT = os.path.join(ROOT, "data", "provenance", "language_labels.csv")
POOL = os.path.join(ROOT, "data", "processed", "candidate_pool.csv")
DECISIONS = os.path.join(ROOT, "data", "interim", "agent_decisions.csv")
VALID = {"fil", "eng", "mixed"}


def read_jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    for line in io.open(path, encoding="utf-8"):
        if line.strip():
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Assemble the language label file")
    ap.add_argument("--out", default=ARTIFACT)
    args = ap.parse_args(argv)

    labels = {}
    source = Counter()

    # 1. the re-label of the original corpus
    if os.path.exists(args.out):
        with io.open(args.out, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                cid = (r.get("comment_id") or "").strip()
                lang = (r.get("language") or "").strip()
                if cid and lang in VALID:
                    labels[cid] = lang
                    source["re-label"] += 1

    # 2 and 3. the adjudicated language of the rows added since
    for d in read_jsonl(DECISIONS):
        cid = d.get("comment_id")
        lang = d.get("language")
        if cid and lang in VALID and cid not in labels:
            labels[cid] = lang
            source["adjudicated"] += 1

    # the language passes over the rows the engine decided on its own
    for pattern in ("lang_auto", "lang_auto2"):
        for f in sorted(glob.glob(os.path.join(ROOT, "data", "interim", pattern,
                                               "out_*.jsonl"))):
            for d in read_jsonl(f):
                cid = d.get("comment_id")
                lang = d.get("language")
                if cid and lang in VALID and cid not in labels:
                    labels[cid] = lang
                    source["language pass"] += 1

    # the pool's own rows, so the artifact covers everything that is shipped
    pool_ids = set()
    if os.path.exists(POOL):
        for r in csv.DictReader(io.open(POOL, encoding="utf-8", newline="")):
            pool_ids.add(r["comment_id"])

    with io.open(args.out, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["comment_id", "language"])
        for cid in sorted(labels):
            w.writerow([cid, labels[cid]])

    covered = len(set(labels) & pool_ids)
    print(f"language labels written : {len(labels)}  -> {args.out}")
    print(f"  from                : {dict(source)}")
    print(f"  covering the pool   : {covered} of {len(pool_ids)} rows")
    print(f"  distribution        : {dict(Counter(labels.values()))}")
    if covered < len(pool_ids):
        print(f"  NOT COVERED         : {len(pool_ids) - covered} rows fall back to the rule")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
