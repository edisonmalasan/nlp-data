"""
test_to_interim.py — assertions for the Stage 1b capture hand-off.

    python tests/run_all.py

Covers the raw snapshot validation, the flattening into interim rows, the
comment_id sequence (global per account, never per post), and the CLI
end to end including the refusal to write a malformed capture.
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

from collect.to_interim import (validate, flatten, looks_official, next_seq,
                                platform_prefix)

SNAP = {
    "run_id": "fb_dost_pagasa_2026-10-20T09-30",
    "source_page": "dost_pagasa",
    "source_page_name": "DOST-PAGASA",
    "platform": "facebook",
    "agency_id": "dost_pagasa",
    "collection_method": "browser_dom_session",
    "tool": "orca-computer-use",
    "collected_at": "2026-10-20T09:30:00+00:00",
    "posts": [
        {
            "post_url": "https://www.facebook.com/PAGASA.DOST.GOV.PH/posts/123456",
            "post_date": "2026-10-19",
            "post_text": "SYABAS: Moderate rainfall expected over Northern Luzon.",
            "post_media_type": "text",
            "post_topic": "weather",
            "scrolled_to_end": True,
            "comments": [
                {"comment_text": "Please repair the damaged road in our barangay.",
                 "author_name": "Juan Dela Cruz", "timestamp_raw": "2 hours ago",
                 "is_reply": False, "parent_comment_text": ""},
                {"comment_text": "Same, please fix ours too.",
                 "author_name": "Maria Santos", "timestamp_raw": "1 hour ago",
                 "is_reply": True,
                 "parent_comment_text": "Please repair the damaged road in our barangay."},
                {"comment_text": "Ang pangit ng kalsada namin.",
                 "author_name": "DOST-PAGASA", "timestamp_raw": "3 hours ago",
                 "is_reply": False, "parent_comment_text": ""},
            ],
        },
        {
            "post_url": "https://www.facebook.com/PAGASA.DOST.GOV.PH/posts/789012",
            "post_date": "2026-10-18",
            "post_text": "Tropical Cyclone Advisory.",
            "post_media_type": "text",
            "post_topic": "weather",
            "scrolled_to_end": True,
            "comments": [
                {"comment_text": "Salamat po!", "author_name": "Ana Reyes",
                 "timestamp_raw": "5 hours ago", "is_reply": False,
                 "parent_comment_text": ""},
            ],
        },
    ],
}


def run() -> list:
    failures = []

    def check(name, got, want):
        if got != want:
            failures.append(f"{name}: got {got!r} want {want!r}")

    # ---- validation ----
    check("a valid snapshot has no problems", validate(SNAP, "snap.json"), [])
    check("a missing posts list is caught",
          bool(validate({"foo": 1}, "bad.json")), True)
    check("an empty comment text is caught",
          bool(validate({"posts": [{"comments": [{"comment_text": "  "}]}]},
                        "bad2.json")), True)

    # ---- platform prefix ----
    check("facebook prefix", platform_prefix("facebook"), "fb")
    check("youtube prefix", platform_prefix("youtube"), "yt")
    check("reddit prefix", platform_prefix("reddit"), "rd")

    # ---- flattening ----
    crows, prows = flatten(SNAP, "snap.json", "dost_pagasa", "facebook",
                           "dost_pagasa", "DOST-PAGASA")
    check("2 posts", len(prows), 2)
    check("4 comments", len(crows), 4)
    # the sequence must be GLOBAL across posts, not per post
    check("comment ids are unique and sequential",
          [r["comment_id"] for r in crows],
          ["fb_dost_pagasa_0001", "fb_dost_pagasa_0002",
           "fb_dost_pagasa_0003", "fb_dost_pagasa_0004"])
    check("post ids carry the platform prefix",
          prows[0]["post_id"].startswith("fb_dost_pagasa_"), True)
    check("post ids differ", prows[0]["post_id"] != prows[1]["post_id"], True)
    check("a reply is flagged", crows[1]["is_reply"], "true")
    check("a top-level comment is not a reply", crows[0]["is_reply"], "false")
    check("the parent text is carried",
          crows[1]["parent_comment_text"],
          "Please repair the damaged road in our barangay.")
    check("the post text is carried onto the comment", crows[0]["post_text"][:6], "SYABAS")
    check("the agency id is carried", crows[0]["agency_id"], "dost_pagasa")
    check("an agency account is detected", crows[2]["author_is_official"], "true")
    check("a citizen account is not", crows[0]["author_is_official"], "false")
    check("the text is verbatim", crows[0]["comment_text"],
          "Please repair the damaged road in our barangay.")
    check("the source snapshot is recorded", crows[0]["source_snapshot"],
          "fb_dost_pagasa_2026-10-20T09-30")

    # ---- continuing the sequence ----
    check("a fresh account starts at 0", next_seq("/nonexistent.csv", "facebook",
                                                   "dost_pagasa"), 0)

    # ---- official detection ----
    check("an agency name is official", looks_official("DOST-PAGASA"), True)
    check("a citizen name is not", looks_official("Juan Dela Cruz"), False)
    check("an empty name is not", looks_official(""), False)

    # ---- end to end through the CLI ----
    tmp = tempfile.mkdtemp(prefix="nlp_to_interim_")
    log = os.path.join(ROOT, "data", "provenance", "collection_log.csv")
    log_backup = None
    if os.path.exists(log):
        log_backup = log + ".bak"
        shutil.copy2(log, log_backup)
    try:
        snapdir = os.path.join(tmp, "raw", "facebook", "dost_pagasa")
        os.makedirs(snapdir)
        with io.open(os.path.join(snapdir, "snap.json"), "w", encoding="utf-8") as fh:
            json.dump(SNAP, fh, ensure_ascii=False)

        outdir = os.path.join(tmp, "interim")
        r = subprocess.run(
            [sys.executable, os.path.join(ROOT, "src", "collect", "to_interim.py"),
             "--snapshot-dir", os.path.join(tmp, "raw", "facebook"),
             "--source-page", "dost_pagasa", "--platform", "facebook",
             "--agency-id", "dost_pagasa", "--outdir", outdir],
            capture_output=True, text=True)
        check("exit code", r.returncode, 0)

        cpath = os.path.join(outdir, "comments_captured.csv")
        ppath = os.path.join(outdir, "posts_captured.csv")
        check("interim comments written", os.path.exists(cpath), True)
        check("interim posts written", os.path.exists(ppath), True)

        crows2 = list(csv.DictReader(io.open(cpath, encoding="utf-8", newline="")))
        check("4 comment rows in the CSV", len(crows2), 4)
        check("the first comment id", crows2[0]["comment_id"], "fb_dost_pagasa_0001")

        if os.path.exists(log):
            logrows = list(csv.DictReader(io.open(log, encoding="utf-8", newline="")))
            check("a run was logged", len(logrows) > 0, True)
            check("the method is recorded", logrows[-1]["collection_method"],
                  "browser_dom_session")
            check("the comment count is logged", logrows[-1]["comments_collected"], "4")

        # a malformed capture must write nothing and say so
        with io.open(os.path.join(snapdir, "bad.json"), "w", encoding="utf-8") as fh:
            json.dump({"run_id": "bad", "posts": "not a list"}, fh)
        r2 = subprocess.run(
            [sys.executable, os.path.join(ROOT, "src", "collect", "to_interim.py"),
             "--snapshot-dir", os.path.join(tmp, "raw", "facebook"),
             "--source-page", "dost_pagasa", "--platform", "facebook",
             "--outdir", outdir],
            capture_output=True, text=True)
        check("a malformed capture exits non-zero", r2.returncode, 1)
        check("and says so", "PROBLEMS" in r2.stdout, True)

    finally:
        if log_backup and os.path.exists(log_backup):
            shutil.move(log_backup, log)
        shutil.rmtree(tmp, ignore_errors=True)

    return failures
