"""
apply_language.py — write the re-labelled language into the dataset.

The `language` column is assigned against ONE written convention for every
row, so the column is internally consistent and can be sliced on. The
convention is `data/interim/language_convention.md`.

    python tools/apply_language.py
    python tools/apply_language.py --check-only
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATCHES = os.path.join(ROOT, "data", "interim", "lang_batches")
FILES = [
    os.path.join(ROOT, "data", "processed", "dataset_full.csv"),
    os.path.join(ROOT, "data", "processed", "dataset_v1.csv"),
    os.path.join(ROOT, "data", "processed", "dataset_v1_ext.csv"),
]
VALID = {"fil", "eng", "mixed"}


def read_rows(path):
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_rows(path, rows, fields):
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def load_labels():
    labels = {}
    conflicts = []
    if not os.path.isdir(BATCHES):
        return labels, conflicts
    for f in sorted(os.listdir(BATCHES)):
        if not (f.startswith("out_") and f.endswith(".jsonl")):
            continue
        for line in io.open(os.path.join(BATCHES, f), encoding="utf-8"):
            if not line.strip():
                continue
            d = json.loads(line)
            cid, lang = d.get("comment_id"), d.get("language")
            if lang not in VALID:
                continue
            if cid in labels and labels[cid] != lang:
                conflicts.append((cid, labels[cid], lang))
            labels[cid] = lang
    return labels, conflicts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Apply the re-labelled language")
    ap.add_argument("--check-only", action="store_true")
    args = ap.parse_args(argv)

    labels, conflicts = load_labels()
    print(f"language labels read : {len(labels)}")
    if conflicts:
        print(f"conflicting labels   : {len(conflicts)} {conflicts[:4]}")
    if not labels:
        print("no language batches found")
        return 1

    total = 0
    changed = 0
    for path in FILES:
        rows = read_rows(path)
        if not rows:
            continue
        n_ch = 0
        for r in rows:
            lang = labels.get(r.get("comment_id"))
            if not lang:
                continue
            total += 1
            if r.get("language") != lang:
                n_ch += 1
            r["language"] = lang
        if n_ch and not args.check_only:
            write_rows(path, rows, list(rows[0].keys()))
        changed += n_ch
        print(f"  {os.path.basename(path):22} {len(rows):>6} rows, {n_ch:>5} changed")
    print(f"\n{total} row-label pairs, {changed} values changed")
    print("  " + str(dict(Counter(labels.values()))))
    if args.check_only:
        print("(check only - nothing written)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
