"""
verification_sample.py — the human verification pass and the blinded
re-label pass.

Two passes, both required before release.

1. **Human verification.** A random sample of at least 100 rows is re-read by
   the researcher, blind: the label is not shown. The agreement rate and
   Cohen's κ against the annotator's label are recorded. If the annotator
   disagrees on more than about 20% of the sample, the cue lists are fixed
   before anything is released.

2. **Blinded re-label.** After a washout of at least seven days, 20% of the
   rows are re-labelled blind and κ is computed between `label` and
   `label_2`. This is the intra-annotator reliability statistic - there is
   one annotator, so it is test-retest, not inter-annotator agreement.

Usage
-----
    # draw the blind sample
    python tools/verification_sample.py sample --n 120 --out data/interim/verify_sample.csv

    # the researcher fills the `human_label` column (0 or 1)
    # score it against the annotator
    python tools/verification_sample.py score --sample data/interim/verify_sample.csv

    # the blinded re-label pass, after the washout
    python tools/verification_sample.py relabel --frac 0.2 --out data/interim/relabel_sample.csv
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import random
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET = os.path.join(ROOT, "data", "processed", "dataset_v1.csv")
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
            "parent_comment_text": (r.get("context_text_norm") or "")[:300],
            "platform": r.get("platform"),
            # the annotator's label is deliberately NOT in the sample
            "human_label": "",
            "human_note": "",
        })
    write_rows(args.out, out, ["comment_id", "comment_text", "post_text",
                               "parent_comment_text", "platform",
                               "human_label", "human_note"])
    print(f"wrote {len(out)} blind rows to {args.out}")
    print("fill the human_label column with 0 or 1, then run the score command")
    return 0


def cmd_score(args):
    sample = read_rows(args.sample)
    ds = {r.get("comment_id"): r for r in read_rows(args.dataset)}
    a, b = [], []
    skipped = 0
    for r in sample:
        hv = (r.get("human_label") or "").strip()
        if hv not in ("0", "1"):
            skipped += 1
            continue
        row = ds.get(r.get("comment_id"))
        if row is None:
            skipped += 1
            continue
        a.append(int(row.get("label")))
        b.append(int(hv))
    if not a:
        print("no rows to score - is the human_label column filled in?")
        return 1
    agree = sum(1 for x, y in zip(a, b) if x == y)
    k = cohens_kappa(a, b)
    print(f"rows scored        : {len(a)}  (skipped {skipped})")
    print(f"agreement rate     : {agree / len(a):.1%}")
    print(f"Cohen's kappa      : {k:.4f}")
    print(f"annotator label 1  : {sum(a)}")
    print(f"human label 1      : {sum(b)}")
    tp = sum(1 for x, y in zip(a, b) if x == 1 and y == 1)
    fp = sum(1 for x, y in zip(a, b) if x == 1 and y == 0)
    fn = sum(1 for x, y in zip(a, b) if x == 0 and y == 1)
    tn = sum(1 for x, y in zip(a, b) if x == 0 and y == 0)
    print(f"confusion (annotator x human): TP={tp} FP={fp} FN={fn} TN={tn}")
    gate = "PASS" if k >= 0.60 else "FAIL - the cue lists need fixing before release"
    print(f"reliability gate (k >= 0.60)   : {gate}")
    return 0


def cmd_relabel(args):
    rows = read_rows(args.dataset)
    rng = random.Random(args.seed)
    k = max(1, int(len(rows) * args.frac))
    picked = rng.sample(rows, min(k, len(rows)))
    out = []
    for r in picked:
        out.append({
            "comment_id": r.get("comment_id"),
            "comment_text": r.get("comment_text_norm") or r.get("comment_text"),
            "post_text": (r.get("post_text") or "")[:400],
            "parent_comment_text": (r.get("context_text_norm") or "")[:300],
            # the label is hidden for the re-label
            "label_2": "",
            "relabel_note": "",
        })
    write_rows(args.out, out, ["comment_id", "comment_text", "post_text",
                               "parent_comment_text", "label_2", "relabel_note"])
    print(f"wrote {len(out)} rows to {args.out}")
    print("re-label them blind, after the washout, then score with --relabel")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="The human verification and re-label passes")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sample", help="draw a blind human-verification sample")
    s.add_argument("--n", type=int, default=120)
    s.add_argument("--seed", type=int, default=SEED)
    s.add_argument("--dataset", default=DATASET)
    s.add_argument("--out", default=os.path.join(ROOT, "data", "interim", "verify_sample.csv"))
    s.set_defaults(fn=cmd_sample)

    s = sub.add_parser("score", help="score the filled-in sample")
    s.add_argument("--sample", default=os.path.join(ROOT, "data", "interim", "verify_sample.csv"))
    s.add_argument("--dataset", default=DATASET)
    s.set_defaults(fn=cmd_score)

    s = sub.add_parser("relabel", help="draw the blinded re-label sample")
    s.add_argument("--frac", type=float, default=0.2)
    s.add_argument("--seed", type=int, default=SEED)
    s.add_argument("--dataset", default=DATASET)
    s.add_argument("--out", default=os.path.join(ROOT, "data", "interim", "relabel_sample.csv"))
    s.set_defaults(fn=cmd_relabel)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
