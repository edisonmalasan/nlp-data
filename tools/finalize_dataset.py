"""
finalize_dataset.py — everything from raw snapshots to the release package.

    python tools/finalize_dataset.py --stage clean
    python tools/finalize_dataset.py --stage all

Stages
------
clean      raw snapshots -> interim -> cleaned candidate pool, with the
           exclusion ledger
score      the cleaned pool -> scored rows + the review batches
apply      the scored rows + the decisions -> the labelled dataset
split      the labelled dataset -> train / dev / test
validate   the acceptance checks (V-01..V-17)
release    the package in data/final/ and the zip
report     the dataset statistics

Every stage is a separate process and can be run on its own, so a failure
in one does not lose the work of the others.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable

RAW = os.path.join(ROOT, "data", "raw")
INTERIM = os.path.join(ROOT, "data", "interim")
PROCESSED = os.path.join(ROOT, "data", "processed")
PROVENANCE = os.path.join(ROOT, "data", "provenance")

POOL = os.path.join(PROCESSED, "candidate_pool.csv")
LEDGER = os.path.join(INTERIM, "exclusion_ledger.csv")
SCORED = os.path.join(INTERIM, "auto_scored.csv")
DECISIONS = os.path.join(INTERIM, "agent_decisions.csv")
FULL = os.path.join(PROCESSED, "dataset_full.csv")
DATASET = os.path.join(PROCESSED, "dataset_v1.csv")
EXT = os.path.join(PROCESSED, "dataset_v1_ext.csv")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def run(label, argv, allow_fail=False):
    log(f"--- {label}")
    r = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    out = (r.stdout or "").strip()
    if out:
        print(out)
    if r.returncode != 0:
        err = (r.stderr or "").strip()
        if err:
            print(err)
        log(f"    {label} exited with code {r.returncode}")
        if not allow_fail:
            raise SystemExit(r.returncode)
        return r.returncode
    return 0


def stage_clean():
    # the interim layer is rebuilt from the raw snapshots every time
    for stale in ("comments_captured.csv", "posts_captured.csv"):
        p = os.path.join(INTERIM, stale)
        if os.path.exists(p):
            os.remove(p)
            log(f"cleared {stale}")

    for platform in ("facebook", "youtube", "x", "reddit"):
        d = os.path.join(RAW, platform)
        if not os.path.isdir(d):
            continue
        for src in sorted(os.listdir(d)):
            sd = os.path.join(d, src)
            if not os.path.isdir(sd):
                continue
            run(f"to_interim {platform}/{src}",
                [PY, os.path.join(ROOT, "src", "collect", "to_interim.py"),
                 "--snapshot-dir", sd,
                 "--source-page", src,
                 "--platform", platform,
                 "--outdir", INTERIM,
                 "--append"], allow_fail=True)

    run("clean", [PY, os.path.join(ROOT, "src", "clean", "pipeline.py"),
                  "--pool", os.path.join(INTERIM, "comments_captured.csv"),
                  "--out", POOL,
                  "--ledger-out", LEDGER,
                  "--report", os.path.join(PROVENANCE, "cleaning_report.json")],
        allow_fail=True)


def stage_score():
    run("score", [PY, os.path.join(ROOT, "src", "annotate", "auto_annotator.py"),
                  "score",
                  "--pool", POOL,
                  "--out", SCORED,
                  "--review-out", os.path.join(INTERIM, "review_batches"),
                  "--batch-size", "50"], allow_fail=True)


def stage_apply():
    # the labelled dataset is written in full first; the primary (Facebook
    # only) and the extension (every platform) are cut from it
    run("apply", [PY, os.path.join(ROOT, "src", "annotate", "auto_annotator.py"),
                   "apply",
                   "--scored", SCORED,
                   "--decisions", DECISIONS,
                   "--out", FULL], allow_fail=True)


def stage_package():
    # build_package must run twice: once after apply so that dataset_v1.csv
    # exists for the splitter, and again after the split so that the split
    # column and counts_by_split in the metadata are current. Running it only
    # inside apply leaves counts_by_split describing the previous split.
    run("package", [PY, os.path.join(ROOT, "tools", "build_package.py")],
        allow_fail=True)


def stage_split():
    run("split", [PY, os.path.join(ROOT, "tools", "split_dataset.py"),
                  "--dataset", DATASET,
                  "--outdir", os.path.join(PROCESSED, "splits"),
                  "--report", os.path.join(PROVENANCE, "split_report.json")],
        allow_fail=True)


def stage_validate():
    run("validate", [PY, os.path.join(ROOT, "tools", "validate_dataset.py"),
                     "--dataset", DATASET,
                     "--outdir", os.path.join(PROCESSED, "splits"),
                     "--report", os.path.join(PROCESSED, "validation_report.txt")],
        allow_fail=True)


def stage_release():
    run("release", [PY, os.path.join(ROOT, "tools", "build_release.py"),
                    "--build", "--zip"], allow_fail=True)


def stage_report():
    run("report", [PY, os.path.join(ROOT, "tools", "dataset_report.py"),
                   "--pool", POOL,
                   "--ledger", LEDGER,
                   "--json", os.path.join(PROVENANCE, "dataset_report.json")],
        allow_fail=True)


STAGES = {
    "clean": stage_clean,
    "score": stage_score,
    "apply": stage_apply,
    "package": stage_package,
    "split": stage_split,
    "validate": stage_validate,
    "release": stage_release,
    "report": stage_report,
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Raw snapshots -> release package")
    ap.add_argument("--stage", default="all",
                    choices=list(STAGES) + ["all"])
    args = ap.parse_args(argv)

    order = ["clean", "score", "apply", "package", "split", "package",
             "validate", "release", "report"]
    chosen = order if args.stage == "all" else [args.stage]
    for s in chosen:
        STAGES[s]()
    log("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
