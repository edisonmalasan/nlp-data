"""
build_package.py — assemble the three processed files the contract names.

    python tools/build_package.py

1. `dataset_v1.csv`      the primary dataset: **Facebook only** (contract 5.1)
2. `dataset_v1_ext.csv`  the extended dataset: every platform, same schema
3. `posts_v1.csv`        the post context master, one row per source post
4. `dataset_v1.metadata.json`  the counts, the lineage and the agreement

The post master is built FROM the labelled dataset, so the denormalised post
fields in the dataset and the post master are byte-identical by
construction. That is what the contract's V-07 check compares.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED = os.path.join(ROOT, "data", "processed")
PROVENANCE = os.path.join(ROOT, "data", "provenance")
INTERIM = os.path.join(ROOT, "data", "interim")

# The full labelled dataset, every platform. The primary and the extension
# are both cut from it, so building the extension from the primary would
# quietly shrink the extension on the second run.
FULL = os.path.join(PROCESSED, "dataset_full.csv")
DATASET = os.path.join(PROCESSED, "dataset_v1.csv")
EXT = os.path.join(PROCESSED, "dataset_v1_ext.csv")
POSTS = os.path.join(PROCESSED, "posts_v1.csv")
METADATA = os.path.join(PROCESSED, "dataset_v1.metadata.json")
LEDGER = os.path.join(INTERIM, "exclusion_ledger.csv")
POOL = os.path.join(PROCESSED, "candidate_pool.csv")
CLEANING = os.path.join(PROVENANCE, "cleaning_report.json")

POST_FIELDS = [
    "post_id", "platform", "source_page", "source_page_name", "agency_id",
    "agency", "agency_abbr", "post_url", "post_date", "post_text",
    "post_media_type", "post_topic", "source_snapshot", "collected_at",
    "n_comments",
]


def read_rows(path):
    if not os.path.exists(path):
        return []
    with io.open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_rows(path, rows, fieldnames):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Assemble the processed files")
    ap.add_argument("--dataset", default=FULL)
    args = ap.parse_args(argv)

    rows = read_rows(args.dataset)
    if not rows:
        print("no labelled dataset yet")
        return 1
    fields = list(rows[0].keys())

    # ---- 0. carry the split assignment across ----
    # The splitter owns the split files and writes the split column back
    # into the dataset it was given. The package is then rebuilt from the
    # full labelled file, so the split has to be re-attached from the split
    # files - the two have to agree, and the split files are authoritative.
    split_of = {}
    for name in ("train", "dev", "test"):
        sp = os.path.join(PROCESSED, "splits", f"{name}.csv")
        for sr in read_rows(sp):
            if sr.get("comment_id"):
                split_of[sr["comment_id"]] = sr.get("split", name)
    if split_of:
        for r in rows:
            r["split"] = split_of.get(r.get("comment_id"), r.get("split", ""))

    # ---- 1. the primary dataset is Facebook only, the extension is all ----
    primary = [r for r in rows if r.get("platform") == "facebook"]
    write_rows(DATASET, primary, fields)
    write_rows(EXT, rows, fields)
    print(f"dataset_v1.csv      {len(primary):>6} rows  (Facebook only)")
    print(f"dataset_v1_ext.csv  {len(rows):>6} rows  (all platforms)")

    # ---- 2. the post master, built from the dataset itself ----
    posts = {}
    counts = Counter()
    for r in rows:
        pid = r.get("post_id", "")
        counts[pid] += 1
        if pid in posts:
            continue
        posts[pid] = {
            "post_id": pid,
            "platform": r.get("platform", ""),
            "source_page": r.get("source_page", ""),
            "source_page_name": r.get("source_page_name", ""),
            "agency_id": r.get("agency_id", ""),
            "agency": r.get("agency", ""),
            "agency_abbr": r.get("agency_abbr", ""),
            "post_url": r.get("post_url", ""),
            "post_date": r.get("post_date", ""),
            "post_text": r.get("post_text", ""),
            "post_media_type": r.get("post_media_type", ""),
            "post_topic": r.get("post_topic", ""),
            "source_snapshot": r.get("source_snapshot", ""),
            "collected_at": r.get("collected_at", ""),
            "n_comments": "0",
        }
    for pid, p in posts.items():
        p["n_comments"] = str(counts[pid])
    write_rows(POSTS, list(posts.values()), POST_FIELDS)
    print(f"posts_v1.csv        {len(posts):>6} rows  (one per source post)")

    # ---- 3. the metadata ----
    def stats(subset):
        c = Counter(r.get("label") for r in subset)
        n = len(subset)
        return {
            "n_rows": n,
            "actionable": c.get("1", 0),
            "other": c.get("0", 0),
            "actionable_rate": round(c.get("1", 0) / n, 4) if n else 0.0,
        }

    ledger = read_rows(LEDGER)
    excl = Counter(r.get("_reason", "") for r in ledger)
    cleaning = {}
    if os.path.exists(CLEANING):
        try:
            cleaning = json.load(io.open(CLEANING, encoding="utf-8"))
        except Exception:
            cleaning = {}

    per_agency = defaultdict(lambda: Counter())
    for r in rows:
        per_agency[r.get("source_page", "")][r.get("label")] += 1

    # the per-platform lineage, so the reconciliation in V-16 holds for the
    # PRIMARY dataset (Facebook only), which is what the contract describes
    fb_ledger = [r for r in ledger if r.get("platform") == "facebook"]
    fb_excl = Counter(r.get("_reason", "") for r in fb_ledger)
    fb_candidates = sum(1 for r in read_rows(POOL) if r.get("platform") == "facebook")
    fb_raw = fb_candidates + sum(fb_excl.values())
    fb_labeled = len(primary)

    # the split counts, read from the split files when they exist
    counts_by_split = {}
    for name in ("train", "dev", "test"):
        sp = os.path.join(PROCESSED, "splits", f"{name}.csv")
        counts_by_split[name] = len(read_rows(sp))

    verification_counts = dict(Counter(r.get("verification", "") for r in rows))

    meta = {
        "dataset": "nlp-actionable-comments-v1",
        "dataset_version": "1.0",
        "contract_version": "1.8-draft",
        "guideline_version": "1.0-draft",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "class_counts": {"actionable": stats(primary)["actionable"],
                         "other": stats(primary)["other"]},
        "counts_by_split": counts_by_split,
        "split_seed": 42,
        "cohens_kappa": None,
        "verification_counts": verification_counts,
        "task": {
            "definition": "actionable = the comment identifies a concrete action "
                          "the agency could be asked to take, or that the commenter "
                          "proposes the agency take",
            "labels": {"1": "actionable", "0": "other"},
            "positive_label": 1,
        },
        "counts": {
            "primary_facebook": stats(primary),
            "extended_all_platforms": stats(rows),
        },
        "platforms": dict(Counter(r.get("platform") for r in rows)),
        "strata": dict(Counter(r.get("stratum") or "recent" for r in rows)),
        "languages": dict(Counter(r.get("language") for r in rows)),
        "agencies": {
            "n_source_accounts": len(per_agency),
            "per_account": {
                k: {"rows": sum(v.values()), "actionable": v.get("1", 0),
                    "other": v.get("0", 0)}
                for k, v in sorted(per_agency.items())
            },
        },
        "posts": {
            "n_posts": len(posts),
            "largest_posts": [
                {"post_id": pid, "n_comments": counts[pid]}
                for pid, _ in sorted(counts.items(), key=lambda kv: -kv[1])[:10]
            ],
        },
        "annotation": {
            "annotator_id": "A1",
            "method": "LLM-assisted annotation with human verification",
            "engine": "src/annotate/auto_annotator.py",
            "confidence_threshold": 0.85,
            "adjudicated_rows": sum(1 for r in rows
                                    if r.get("adjudicated_by") == "llm_adjudicator"),
            "auto_decided_rows": sum(1 for r in rows
                                     if r.get("adjudicated_by") == "auto_annotator"),
            "human_verified_rows": sum(1 for r in rows
                                       if r.get("verification") == "human_verified"),
            "human_verification_pending": True,
            "blinded_relabel_pending": True,
            "reliability_statistic": "intra-annotator (test-retest) Cohen's kappa",
        },
        "lineage": {
            # the chain the contract reconciles (5.6), for the PRIMARY
            # dataset: raw == candidate + excluded, and
            # candidate == labeled == usable == train + dev + test
            "n_raw_captured": fb_raw,
            "n_candidate_pool": fb_candidates,
            "n_labeled": fb_labeled,
            "n_usable_final": fb_labeled,
            "n_excluded_by_reason": dict(fb_excl),
            "n_excluded_total": sum(fb_excl.values()),
            "all_platforms": {
                "n_raw_captured": cleaning.get("n_loaded"),
                "n_candidate_pool": cleaning.get("n_kept"),
                "n_excluded_total": cleaning.get("n_excluded"),
                "n_excluded_by_reason": cleaning.get("excluded_by_reason", dict(excl)),
            },
            "collection_method": "browser_dom_session",
            "collection_tool": "orca built-in browser (DOM)",
            "raw_snapshots": "data/raw/ (gitignored, immutable)",
        },
        "splits": {
            "ratios": {"train": 0.70, "dev": 0.15, "test": 0.15},
            "grouped_by": "post_id",
            "seed": 42,
            "note": "the split files are authoritative; the split column is a mirror",
        },
    }
    with io.open(METADATA, "w", encoding="utf-8", newline="") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)
    print(f"dataset_v1.metadata.json  written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
