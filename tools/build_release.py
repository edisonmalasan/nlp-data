"""
build_release.py — assemble the final dataset package into data/final/.

The release package is the single artifact the modeling stage receives. This script
builds it reproducibly from data/processed/ and data/provenance/, writes a manifest with
checksums and counts, and can produce the zip.

Usage
-----
    python tools/build_release.py --check
    python tools/build_release.py --build
    python tools/build_release.py --build --zip

--check  verify the release can be built (files present, validation report clean)
--build  assemble data/final/ and write MANIFEST.json
--zip    also write data/final/nlp-actionable-comments-v1.zip
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import zipfile
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FINAL = os.path.join(ROOT, "data", "final")

PACKAGE_NAME = "nlp-actionable-comments-v1"

# Files copied into the package, relative to the repo root.
PACKAGE_FILES = [
    "data/processed/dataset_v1.csv",
    "data/processed/dataset_v1_ext.csv",
    "data/processed/posts_v1.csv",
    "data/processed/dataset_v1.metadata.json",
    "data/processed/splits/train.csv",
    "data/processed/splits/dev.csv",
    "data/processed/splits/test.csv",
    "data/provenance/government_agencies.csv",
    "docs/ANNOTATION_GUIDELINES.md",
]


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            h.update(block)
    return h.hexdigest()


def csv_rows(path: str) -> list:
    import csv

    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def count_labels(path: str) -> dict:
    rows = csv_rows(path)
    actionable = sum(1 for r in rows if r.get("label") == "1")
    other = sum(1 for r in rows if r.get("label") == "0")
    llm_verified = sum(1 for r in rows if r.get("verification") == "llm_verified")
    human_verified = sum(
        1 for r in rows if r.get("verification", "") in ("human_verified", "human_labeled")
    )
    verified = llm_verified + human_verified
    return {
        "n_rows": len(rows),
        "actionable": actionable,
        "other": other,
        "actionable_rate": round(actionable / len(rows), 4) if rows else 0.0,
        "n_verified": verified,
        "verified_rate": round(verified / len(rows), 4) if rows else 0.0,
        "n_llm_verified": llm_verified,
        "n_human_verified": human_verified,
    }


def do_check() -> int:
    problems = []
    for rel in PACKAGE_FILES:
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            problems.append(f"missing: {rel}")
        elif os.path.getsize(p) == 0:
            problems.append(f"empty: {rel}")

    ds = os.path.join(ROOT, "data", "processed", "dataset_v1.csv")
    if os.path.exists(ds):
        stats = count_labels(ds)
        if stats["n_rows"] == 0:
            problems.append("dataset_v1.csv has no rows - not ready to release")

    report = os.path.join(ROOT, "data", "processed", "validation_report.txt")
    if os.path.exists(report):
        body = open(report, encoding="utf-8").read().lower()
        if "error" in body and "0 errors" not in body:
            problems.append("validation_report.txt reports errors")
    else:
        problems.append("missing: data/processed/validation_report.txt")

    if problems:
        print("NOT READY TO RELEASE:")
        for p in problems:
            print(f"  - {p}")
        return 1

    print("READY TO RELEASE")
    print(f"  {count_labels(ds)}")
    return 0


def do_build(args) -> int:
    if args.check:
        return do_check()

    missing = [r for r in PACKAGE_FILES if not os.path.exists(os.path.join(ROOT, r))]
    if missing:
        print("Cannot build, missing:")
        for m in missing:
            print(f"  - {m}")
        return 1

    if os.path.isdir(FINAL):
        for name in os.listdir(FINAL):
            # Keep the package README - it is written by hand, not generated.
            if name == "README.md":
                continue
            p = os.path.join(FINAL, name)
            if os.path.isdir(p):
                shutil.rmtree(p)
            else:
                os.remove(p)
    else:
        os.makedirs(FINAL)

    manifest_files = []
    readme = os.path.join(FINAL, "README.md")
    if os.path.exists(readme):
        manifest_files.append({
            "source": "data/final/README.md",
            "packaged_as": "README.md",
            "bytes": os.path.getsize(readme),
            "sha256": sha256(readme),
        })
    for rel in PACKAGE_FILES:
        src = os.path.join(ROOT, rel)
        dst = os.path.join(FINAL, os.path.basename(rel))
        shutil.copy2(src, dst)
        manifest_files.append({
            "source": rel,
            "packaged_as": os.path.basename(rel),
            "bytes": os.path.getsize(dst),
            "sha256": sha256(dst),
        })

    ds = os.path.join(FINAL, "dataset_v1.csv")
    stats = count_labels(ds)

    splits = {}
    for name in ("train", "dev", "test"):
        p = os.path.join(FINAL, f"{name}.csv")
        if os.path.exists(p):
            splits[name] = len(csv_rows(p))

    meta_path = os.path.join(FINAL, "dataset_v1.metadata.json")
    meta = {}
    if os.path.exists(meta_path):
        meta = json.load(open(meta_path, encoding="utf-8"))

    manifest = {
        "package": PACKAGE_NAME,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "builder": "tools/build_release.py",
        "dataset_version": meta.get("dataset_version", "v1"),
        "guideline_version": meta.get("guideline_version", ""),
        "label_encoding": {"1": "actionable", "0": "other"},
        "counts": stats,
        "split_counts": splits,
        "files": manifest_files,
    }
    with open(os.path.join(FINAL, "MANIFEST.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    print(f"Package written to {FINAL}")
    print(f"  {stats['n_rows']} rows  ({stats['actionable']} actionable / {stats['other']} other)")
    print(f"  splits: {splits}")
    print(f"  verified: {stats['n_verified']} ({stats['verified_rate']:.1%}) "
          f"[llm={stats['n_llm_verified']} human={stats['n_human_verified']}]")
    print(f"  files: {len(manifest_files)} + MANIFEST.json")

    if args.zip:
        zip_path = os.path.join(FINAL, f"{PACKAGE_NAME}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in sorted(os.listdir(FINAL)):
                if name.endswith(".zip"):
                    continue
                zf.write(os.path.join(FINAL, name), arcname=f"{PACKAGE_NAME}/{name}")
        print(f"  zip: {zip_path} ({os.path.getsize(zip_path) / 1024:.1f} KB)")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--build", action="store_true", help="assemble the package")
    ap.add_argument("--check", action="store_true", help="verify readiness only")
    ap.add_argument("--zip", action="store_true", help="also write the zip archive")
    args = ap.parse_args(argv)

    if not args.build:
        return do_check()
    return do_build(args)


if __name__ == "__main__":
    sys.exit(main())
