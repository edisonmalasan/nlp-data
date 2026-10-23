"""
verification_sample.py — the independent verification pass and the blinded
re-label pass.

Two passes, both required before release.

1. **Independent verification.** A random sample of at least 100 rows is
   re-read blind: the label is not shown. The agreement rate and Cohen's kappa
   against the annotator's label are recorded. If the annotator disagrees on
   more than about 20% of the sample, the cue lists are fixed before anything
   is released. The verifier may be a person (`human_verified`) or a model
   annotator (`llm_verified`); the method is recorded, never inferred.

2. **Blinded re-label.** 20% of the rows are re-labelled blind and kappa is
   computed between `label` and `label_2`. This is the intra-annotator
   reliability statistic - there is one annotator. A washout of >= 7 days is
   required for a true test-retest; if the pass is run without one, record
   `--washout-days 0` and report kappa as an upper bound.

Usage
-----
    # draw the blind samples
    python tools/verification_sample.py sample  --n 120 --out data/interim/verify_sample.csv
    python tools/verification_sample.py relabel --frac 0.2 --out data/interim/relabel_sample.csv

    # fill `verified_label` / `label_2` with 0 or 1, then merge the results
    python tools/verification_sample.py merge \\
        --dataset data/processed/dataset_full.csv \\
        --verify data/interim/verify_sample.csv \\
        --relabel data/interim/relabel_sample.csv \\
        --method llm_assisted --verifier "independent model pass" --washout-days 0
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import random
from collections import Counter
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET = os.path.join(ROOT, "data", "processed", "dataset_v1.csv")
RELIABILITY = os.path.join(ROOT, "data", "provenance", "reliability.json")
SEED = 42


def read_rows(path):
    with io.open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_rows(path, rows, fields):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def cohens_kappa(a, b):
    """Cohen's kappa for two label sequences of 0/1."""
    n = len(a)
    if n == 0:
        return 0.0
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    ca, cb = Counter(a), Counter(b)
    pe = sum((ca[v] / n) * (cb[v] / n) for v in (0, 1))
    if pe == 1:
        return 1.0
    return (po - pe) / (1 - pe)


SAMPLE_FIELDS = ["comment_id", "comment_text", "post_text", "post_context",
                 "platform", "verified_label", "verified_note"]
RELABEL_FIELDS = ["comment_id", "comment_text", "post_text", "post_context",
                  "label_2", "relabel_note"]


def _context(r):
    """The post context, already normalized, without the [POST] marker."""
    ctx = (r.get("context_text_norm") or "").strip()
    if ctx.startswith("[POST]"):
        ctx = ctx[len("[POST]"):].strip()
    return ctx[:300]


def cmd_sample(args):
    rows = read_rows(args.dataset)
    rng = random.Random(args.seed)
    picked = rng.sample(rows, min(args.n, len(rows)))
    out = []
    for r in picked:
        out.append({
            "comment_id": r.get("comment_id"),
            "comment_text": r.get("comment_text_norm") or r.get("comment_text"),
            "post_text": (r.get("post_text") or "")[:400],
            "post_context": _context(r),
            "platform": r.get("platform"),
            # the annotator's label is deliberately NOT in the sample
            "verified_label": "",
            "verified_note": "",
        })
    write_rows(args.out, out, SAMPLE_FIELDS)
    print(f"wrote {len(out)} blind rows to {args.out}")
    print("fill verified_label with 0 or 1, then run the merge command")
    return 0


def cmd_relabel(args):
    rows = read_rows(args.dataset)
    rng = random.Random(args.seed)
    k = max(1, math.ceil(len(rows) * args.frac))
    picked = rng.sample(rows, min(k, len(rows)))
    out = []
    for r in picked:
        out.append({
            "comment_id": r.get("comment_id"),
            "comment_text": r.get("comment_text_norm") or r.get("comment_text"),
            "post_text": (r.get("post_text") or "")[:400],
            "post_context": _context(r),
            # the label is hidden for the re-label
            "label_2": "",
            "relabel_note": "",
        })
    write_rows(args.out, out, RELABEL_FIELDS)
    print(f"wrote {len(out)} rows to {args.out}")
    print("re-label them blind, then run the merge command")
    return 0


def _score(a, b):
    agree = sum(1 for x, y in zip(a, b) if x == y)
    tp = sum(1 for x, y in zip(a, b) if x == 1 and y == 1)
    fp = sum(1 for x, y in zip(a, b) if x == 1 and y == 0)
    fn = sum(1 for x, y in zip(a, b) if x == 0 and y == 1)
    tn = sum(1 for x, y in zip(a, b) if x == 0 and y == 0)
    return {
        "n": len(a),
        "agreement": round(agree / len(a), 4) if a else 0.0,
        "kappa": round(cohens_kappa(a, b), 4),
        "annotator_label_1": sum(a),
        "second_label_1": sum(b),
        "confusion": {"TP": tp, "FP": fp, "FN": fn, "TN": tn},
    }


def cmd_merge(args):
    rows = read_rows(args.dataset)
    by_id = {r.get("comment_id"): r for r in rows}

    verify = read_rows(args.verify) if os.path.exists(args.verify) else []
    relabel = read_rows(args.relabel) if os.path.exists(args.relabel) else []

    va, vb = [], []
    for r in verify:
        v = (r.get("verified_label") or "").strip()
        if v not in ("0", "1"):
            continue
        row = by_id.get(r.get("comment_id"))
        if row is None:
            continue
        va.append(int(row.get("label")))
        vb.append(int(v))
        row["verification"] = args.verification_value

    ra, rb = [], []
    for r in relabel:
        v = (r.get("label_2") or "").strip()
        if v not in ("0", "1"):
            continue
        row = by_id.get(r.get("comment_id"))
        if row is None:
            continue
        row["label_2"] = v
        row["agreement"] = "true" if (row.get("label") or "") == v else "false"
        ra.append(int(row.get("label")))
        rb.append(int(v))

    write_rows(args.dataset, rows, list(rows[0].keys()))

    vstats = _score(va, vb)
    rstats = _score(ra, rb)
    reliability = {
        "verification_method": args.method,
        "method_label": args.method_label,
        "verifier": args.verifier,
        "verified_n": vstats["n"],
        "verification_agreement": vstats["agreement"],
        "verification_kappa": vstats["kappa"],
        "verification_confusion": vstats["confusion"],
        "relabel_n": rstats["n"],
        "relabel_agreement": rstats["agreement"],
        "relabel_kappa": rstats["kappa"],
        "relabel_confusion": rstats["confusion"],
        "relabel_washout_days": args.washout_days,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    os.makedirs(os.path.dirname(RELIABILITY), exist_ok=True)
    with io.open(RELIABILITY, "w", encoding="utf-8", newline="") as fh:
        json.dump(reliability, fh, indent=2)

    print(f"verified rows      : {vstats['n']}")
    print(f"  agreement        : {vstats['agreement']:.1%}")
    print(f"  Cohen's kappa    : {vstats['kappa']:.4f}")
    print(f"  confusion        : {vstats['confusion']}")
    print(f"re-labeled rows    : {rstats['n']}")
    print(f"  agreement        : {rstats['agreement']:.1%}")
    print(f"  Cohen's kappa    : {rstats['kappa']:.4f}")
    print(f"  confusion        : {rstats['confusion']}")
    print(f"  washout (days)   : {args.washout_days}")
    gate = "PASS" if rstats["kappa"] >= 0.60 else "FAIL - the cue lists need fixing before release"
    print(f"reliability gate (k >= 0.60): {gate}")
    print(f"reliability -> {RELIABILITY}")
    print(f"dataset      -> {args.dataset}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Verification and re-label passes")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sample", help="draw a blind verification sample")
    s.add_argument("--n", type=int, default=120)
    s.add_argument("--seed", type=int, default=SEED)
    s.add_argument("--dataset", default=DATASET)
    s.add_argument("--out", default=os.path.join(ROOT, "data", "interim", "verify_sample.csv"))
    s.set_defaults(fn=cmd_sample)

    s = sub.add_parser("relabel", help="draw the blinded re-label sample")
    s.add_argument("--frac", type=float, default=0.2)
    s.add_argument("--seed", type=int, default=SEED)
    s.add_argument("--dataset", default=DATASET)
    s.add_argument("--out", default=os.path.join(ROOT, "data", "interim", "relabel_sample.csv"))
    s.set_defaults(fn=cmd_relabel)

    s = sub.add_parser("merge", help="merge the filled samples back into the dataset")
    s.add_argument("--dataset", default=os.path.join(ROOT, "data", "processed", "dataset_full.csv"))
    s.add_argument("--verify", default=os.path.join(ROOT, "data", "interim", "verify_sample.csv"))
    s.add_argument("--relabel", default=os.path.join(ROOT, "data", "interim", "relabel_sample.csv"))
    s.add_argument("--verification-value", default="llm_verified",
                   choices=["llm_verified", "human_verified", "human_labeled"])
    s.add_argument("--method", default="llm_assisted",
                   choices=["llm_assisted", "human", "mixed"])
    s.add_argument("--method-label",
                   default="LLM-assisted annotation with independent model verification")
    s.add_argument("--verifier", default="independent model pass")
    s.add_argument("--washout-days", type=int, default=0)
    s.set_defaults(fn=cmd_merge)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
