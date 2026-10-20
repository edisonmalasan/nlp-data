"""
test_split_validate.py — assertions for Stage 4 and Stage 5.

    python tests/run_all.py

Builds a synthetic labeled corpus, splits it, and runs the acceptance test
against it. The corpus deliberately has one post per label majority so the
post-grouping constraint is actually exercised.
"""

from __future__ import annotations

import csv
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

CONTRACT = next(csv.reader(io.open(
    os.path.join(ROOT, "data", "processed", "dataset_v1.csv"),
    encoding="utf-8", newline="")))

AGENCY_HDR = ["agency_id", "agency_name", "agency_abbr", "agency_type",
              "parent_department", "parent_department_abbr", "official_website",
              "official_account_url", "official_account_id", "official_account_name",
              "platform", "source_page", "official_verified", "verification_basis",
              "comments_enabled", "domains", "eligibility_s1", "eligibility_s2",
              "eligibility_s3", "eligibility_s4", "eligibility_s5", "eligibility_s6",
              "n_posts_planned", "collection_method", "notes"]

POSTS_HDR = ["post_id", "platform", "source_page", "source_page_name", "agency_id",
              "agency", "agency_abbr", "post_url", "post_date", "post_text",
              "post_media_type", "post_topic", "source_snapshot", "collected_at",
              "n_comments"]


def _build_corpus(tmp):
    """40 posts, ~986 comments, alternating dominant label."""
    rows = []
    cid = 0
    for post in range(40):
        post_id = f"po{post:03d}"
        dominant = "1" if post % 2 == 0 else "0"
        for i in range(20 + (post % 11)):
            cid += 1
            label = dominant if i % 5 else ("0" if dominant == "1" else "1")
            text = f"Comment {cid} sa post {post_id}"
            r = {k: "" for k in CONTRACT}
            r.update({
                "comment_id": f"fb_pagasa_{cid:04d}",
                "platform": "facebook", "source_page": "pagasa",
                "source_page_name": "PAGASA", "agency_id": "dost_pagasa",
                "agency": "Philippine Atmospheric...",
                "agency_abbr": "DOST-PAGASA", "post_id": post_id,
                "post_url": f"https://facebook.com/p/{post_id}",
                "post_date": "2026-10-20", "post_text": f"Advisory {post_id}",
                "post_media_type": "text", "post_topic": "weather",
                "is_reply": "false", "parent_comment_id": "", "parent_comment_text": "",
                "comment_text": text, "comment_text_norm": text,
                "context_text_norm": f"[POST] Advisory {post_id}",
                "dedup_key": f"comment {cid} sa post {post_id}",
                "n_tokens": len(text.split()), "language": "fil", "label": label,
                "label_str": "actionable" if label == "1" else "other",
                "annotator_id": "A1", "label_2": "", "agreement": "",
                "adjudicated_by": "", "adjudication_note": "",
                "guideline_version": "v1.0-draft", "source_snapshot": "run1",
                "collected_at": "2026-10-20T00:00:00Z", "pii_redacted": "false",
                "verification": "auto", "split": "", "notes": "",
                "annotation_rule": "adjudicated", "annotation_evidence": "test",
                "annotation_confidence": "1.0",
            })
            rows.append(r)

    ds = os.path.join(tmp, "dataset_v1.csv")
    with io.open(ds, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CONTRACT, lineterminator="\n")
        w.writeheader()
        for r in rows:
            w.writerow(r)

    posts = os.path.join(tmp, "posts_v1.csv")
    with io.open(posts, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(POSTS_HDR)
        for post in range(40):
            pid = f"po{post:03d}"
            w.writerow([pid, "facebook", "pagasa", "PAGASA", "dost_pagasa",
                        "Philippine Atmospheric...", "DOST-PAGASA",
                        f"https://facebook.com/p/{pid}", "2026-10-20",
                        f"Advisory {pid}", "text", "weather", "run1",
                        "2026-10-20T00:00:00Z", "30"])

    agencies = os.path.join(tmp, "agencies.csv")
    with io.open(agencies, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(AGENCY_HDR)
        w.writerow(["dost_pagasa", "Philippine Atmospheric...", "DOST-PAGASA",
                    "national_government_agency",
                    "Department of Science and Technology", "DOST",
                    "https://pagasa.dost.gov.ph", "https://facebook.com/PAGASA",
                    "123", "PAGASA", "facebook", "pagasa", "true",
                    "linked_from_official_website", "true", "weather",
                    "true", "true", "true", "true", "true", "true", "40",
                    "dom_headless", ""])
    return ds, posts, agencies, len(rows)


def run() -> list:
    failures = []

    def check(name, got, want):
        if got != want:
            failures.append(f"{name}: got {got!r} want {want!r}")

    tmp = tempfile.mkdtemp(prefix="nlp_split_")
    try:
        ds, posts, agencies, n_rows = _build_corpus(tmp)
        outdir = os.path.join(tmp, "splits")

        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "split_dataset.py"),
                            "--dataset", ds, "--outdir", outdir],
                           capture_output=True, text=True)
        check("splitter exit code", r.returncode, 0)

        splits = {}
        for s in ("train", "dev", "test"):
            splits[s] = list(csv.DictReader(io.open(
                os.path.join(outdir, f"{s}.csv"), encoding="utf-8", newline="")))

        ids = [x["comment_id"] for v in splits.values() for x in v]
        check("every row is in exactly one split", len(ids), n_rows)
        check("no comment is in two splits", len(set(ids)), n_rows)

        post_splits = {}
        for s, v in splits.items():
            for x in v:
                post_splits.setdefault(x["post_id"], set()).add(s)
        leaked = {p: v for p, v in post_splits.items() if len(v) > 1}
        check("no post straddles two splits", leaked, {})

        # determinism
        outdir2 = os.path.join(tmp, "splits2")
        subprocess.run([sys.executable, os.path.join(ROOT, "tools", "split_dataset.py"),
                        "--dataset", ds, "--outdir", outdir2],
                       capture_output=True, text=True)
        same = all(
            [x["comment_id"] for x in csv.DictReader(io.open(
                os.path.join(outdir, f"{s}.csv"), encoding="utf-8", newline=""))]
            == [x["comment_id"] for x in csv.DictReader(io.open(
                os.path.join(outdir2, f"{s}.csv"), encoding="utf-8", newline=""))]
            for s in ("train", "dev", "test"))
        check("the split is deterministic", same, True)

        # the split column must match the files, and the header must stay clean
        header = next(csv.reader(io.open(ds, encoding="utf-8", newline="")))
        check("dataset header unchanged", header, CONTRACT)

        # ---- make the metadata consistent, then run the acceptance test ----
        rows = list(csv.DictReader(io.open(ds, encoding="utf-8", newline="")))
        for i, x in enumerate(rows):
            if i % 5 == 0:
                x["label_2"] = x["label"]
                x["agreement"] = "true"
            if i < 120:
                x["verification"] = "human_verified"
        with io.open(ds, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=CONTRACT, lineterminator="\n")
            w.writeheader()
            for x in rows:
                x.pop("_split", None)
                w.writerow(x)

        n_act = sum(1 for x in rows if x["label"] == "1")
        n_oth = len(rows) - n_act
        excl = {"X_DUP_EXACT": 40, "X_SPAM": 60, "X_EMPTY": 20, "X_LANG": 20, "X_PII": 20}
        candidate = len(rows)
        raw = candidate + sum(excl.values())
        meta = {
            "dataset_version": "v1", "guideline_version": "v1.0-draft", "split_seed": 42,
            "class_counts": {"actionable": n_act, "other": n_oth,
                              "actionable_rate": round(n_act / len(rows), 4)},
            "counts_by_split": {k: len(v) for k, v in splits.items()},
            "cohens_kappa": 0.78,
            "verification_counts": {"auto": len(rows) - 120, "human_verified": 120,
                                     "human_labeled": 0},
            "lineage": {
                "n_raw_captured": raw, "n_extracted_to_interim": raw,
                "n_excluded_by_reason": excl, "n_candidate_pool": candidate,
                "n_labeled": candidate, "n_usable_final": candidate,
                "reconciles": True,
            },
        }
        meta_path = os.path.join(tmp, "metadata.json")
        json.dump(meta, io.open(meta_path, "w", encoding="utf-8"), indent=2)

        report = os.path.join(tmp, "validation_report.txt")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "validate_dataset.py"),
                            "--dataset", ds, "--outdir", outdir, "--agencies", agencies,
                            "--posts", posts, "--metadata", meta_path,
                            "--report", report],
                           capture_output=True, text=True)
        check("validator exit code", r.returncode, 0)
        if r.returncode != 0:
            failures.append("validator reported errors:\n" + r.stdout)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    return failures
