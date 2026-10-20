"""
split_dataset.py — Stage 4. Assign comments to train / dev / test.

Implements DATA_CONTRACT.md 12.

  * 70 / 15 / 15
  * stratified by label
  * GROUPED BY post_id - the same post's comments never straddle two splits
  * fixed seed (42), recorded in the metadata

Grouping by post is not optional. Comments on the same post share vocabulary and
context, so a post whose comments appear in both train and test inflates the
score. The label stratification therefore has to happen at the level of whole
posts, not individual rows.

The assignment is a greedy balancing pass: posts are placed largest-first into
whichever split brings the split's per-label counts closest to target.

Usage
-----
    python tools/split_dataset.py \\
        --dataset data/processed/dataset_v1.csv \\
        --outdir  data/processed/splits \\
        --seed    42
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from collections import defaultdict

RATIOS = {"train": 0.70, "dev": 0.15, "test": 0.15}
DEFAULT_SEED = 42
SPLIT_FIELDS = ["comment_id", "split", "platform", "source_page", "post_id", "label"]


def load_rows(path: str) -> list:
    with io.open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_rows(path: str, rows: list, fieldnames: list) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def assign_splits(rows: list, seed: int = DEFAULT_SEED) -> dict:
    """Assign a split to every comment. Returns {comment_id: split}.

    Whole posts move together. The pass is deterministic: same input, same
    output, every time. The seed is accepted and recorded so the run is
    reproducible and auditable.
    """
    # ---- group by post ----
    groups = defaultdict(list)
    for r in rows:
        key = (r.get("source_page", ""), r.get("post_id", ""))
        groups[key].append(r)

    # ---- label totals, for the targets ----
    label_totals = defaultdict(int)
    for r in rows:
        label_totals[r.get("label", "")] += 1

    targets = {
        split: {lab: int(round(total * ratio)) for lab, total in label_totals.items()}
        for split, ratio in RATIOS.items()
    }

    # ---- current counts per split ----
    current = {split: defaultdict(int) for split in RATIOS}

    # ---- place posts, largest first ----
    ordered_groups = sorted(
        groups.items(),
        key=lambda kv: (-len(kv[1]), kv[0][0], kv[0][1]),
    )

    for _key, members in ordered_groups:
        group_counts = defaultdict(int)
        for m in members:
            group_counts[m.get("label", "")] += 1

        best_split = None
        best_cost = None
        for split in ("train", "dev", "test"):
            cost = 0.0
            for lab in set(list(group_counts) + list(targets[split])):
                target = targets[split].get(lab, 0)
                before = current[split].get(lab, 0)
                after = before + group_counts.get(lab, 0)
                cost += (after - target) ** 2 - (before - target) ** 2
            # deterministic tie-break: train > dev > test
            if best_cost is None or cost < best_cost - 1e-9:
                best_cost = cost
                best_split = split

        for lab, n in group_counts.items():
            current[best_split][lab] += n
        for m in members:
            m["_split"] = best_split

    return {r["comment_id"]: r.get("_split") for r in rows if r.get("comment_id")}


def class_prior(rows: list) -> dict:
    n = len(rows)
    if not n:
        return {"actionable": 0.0, "other": 0.0, "n": 0}
    act = sum(1 for r in rows if r.get("label") == "1")
    return {
        "actionable": round(act / n, 4),
        "other": round((n - act) / n, 4),
        "n": n,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Stage 4 - split the labeled dataset")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--report", default=None)
    args = ap.parse_args(argv)

    rows = load_rows(args.dataset)
    if not rows:
        print(f"ERROR: {args.dataset} has no rows.")
        return 1

    labeled = [r for r in rows if r.get("label") in ("0", "1")]
    unlabeled = [r for r in rows if r.get("label") not in ("0", "1")]
    if unlabeled:
        print(f"WARNING: {len(unlabeled)} rows have no label and will be skipped.")
    if not labeled:
        print("ERROR: no labeled rows to split.")
        return 1

    assign_splits(labeled, seed=args.seed)

    # The split column is filled in BEFORE the split files are written. The
    # contract's split schema has a `split` column (5.4), and writing the
    # files while the value was still in the scratch key left that column
    # empty - so the files and the dataset column did not agree, and the
    # validator's V-10 check failed on every row.
    for r in labeled:
        r["split"] = r.get("_split", "")

    buckets = {"train": [], "dev": [], "test": []}
    for r in labeled:
        buckets[r["_split"]].append(r)

    total = len(labeled)
    for name, bucket in buckets.items():
        out = os.path.join(args.outdir, f"{name}.csv")
        write_rows(out, bucket, SPLIT_FIELDS)
        print(f"  {name:5} {len(bucket):>5} rows  ({len(bucket)/total:.1%})  -> {out}")

    # write the split column back into the dataset.
    # The scratch key `_split` must not leak into the header: the contract
    # fixes the column list, and the validator checks the order.
    SCRATCH = {"_split", "_reason", "_rule", "_dup_of"}
    fieldnames = [k for k in rows[0].keys() if k not in SCRATCH]
    if "split" not in fieldnames:
        fieldnames.append("split")
    for r in rows:
        r["split"] = r.pop("_split", r.get("split", ""))
    write_rows(args.dataset, rows, fieldnames)
    print(f"  split column written back into {args.dataset} ({len(fieldnames)} columns)")

    # report
    priors = {name: class_prior(bucket) for name, bucket in buckets.items()}
    print("\nclass prior per split:")
    for name, p in priors.items():
        print(f"  {name:5} actionable={p['actionable']:.3f} other={p['other']:.3f} n={p['n']}")

    drift = abs(priors["test"]["actionable"] - priors["train"]["actionable"])
    print(f"\ntest-vs-train prior drift: {drift:.3f} "
          f"({'OK' if drift <= 0.10 else 'FAILS check V-15 (<= 0.10)'})")

    report = {
        "seed": args.seed,
        "ratios": RATIOS,
        "n_labeled": total,
        "n_unlabeled_skipped": len(unlabeled),
        "counts": {k: len(v) for k, v in buckets.items()},
        "class_prior": priors,
        "test_vs_train_prior_drift": round(drift, 4),
        "grouped_by": "post_id",
    }
    if args.report:
        os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
        with io.open(args.report, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        print(f"report -> {args.report}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
