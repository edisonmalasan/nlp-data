"""
test_clean.py — assertions for the Stage 2 cleaning package.

    python tests/run_all.py

Covers the normalization rules of contract 6.2, the context assembly of 6.3, the
dedup key of 6.6, the duplicate rules of 7, the spam rules of 8, the anonymization
of 11, and the order of the cleaning chain.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from clean.normalize import normalize_text, dedup_key, build_context, token_count
from clean.dedup import is_near_duplicate, dedupe_dataset
from clean.spam import filter_spam, is_repeated_token
from clean.pii import scrub_text
from clean.pipeline import clean, ledger_counts


def run() -> list:
    failures = []

    def check(name, got, want):
        if got != want:
            failures.append(f"{name}: got {got!r} want {want!r}")

    # ---- normalization (contract 6.2) ----
    check("url", normalize_text("see https://facebook.com/page for details"),
          "see <URL> for details")
    check("mention", normalize_text("hi @JuanDelaCruz please help"),
          "hi <USER> please help")
    # the email rule must run before the URL and mention rules
    check("email", normalize_text("contact juan@dept.gov.ph now"),
          "contact <EMAIL> now")
    check("phone", normalize_text("call 09171234567 now"), "call <PHONE> now")
    check("long digits", normalize_text("permit 1234567 expired"), "permit <NUM> expired")
    check("short digits kept", normalize_text("wait 30 mins"), "wait 30 mins")
    check("casing kept", normalize_text("Please Fix The Road"), "Please Fix The Road")
    check("emoji kept", normalize_text("salamat po \U0001f64f"), "salamat po \U0001f64f")
    check("punctuation kept", normalize_text("bakit?! ayoko na..."), "bakit?! ayoko na...")
    check("whitespace collapsed", normalize_text("a    b\n\tc  "), "a b c")
    check("zero width removed", normalize_text("a\u200bb\u200fc"), "abc")
    check("empty safe", normalize_text(""), "")
    check("none safe", normalize_text(None), "")

    # ---- dedup key (contract 6.6) ----
    check("dedup key", dedup_key("Ang Pangit ng Kalsada!"), "ang pangit ng kalsada")
    check("dedup key empty", dedup_key(""), "")

    # ---- context (contract 6.3) ----
    check("context both", build_context("Post text", "Parent text"),
          "[POST] Post text [COMMENT_PARENT] Parent text")
    check("context post only", build_context("Post text", ""), "[POST] Post text")
    check("context parent only", build_context("", "Parent text"),
          "[COMMENT_PARENT] Parent text")
    check("context none", build_context("", ""), "")

    # ---- near duplicate (contract 7.2) ----
    check("identical is near", is_near_duplicate("fix the road please", "fix the road please"), True)
    # token sets differ by one: 7/8 = 0.875, which is below 0.90
    check("jaccard 0.875 is not near",
          is_near_duplicate("please fix the road in our barangay now",
                            "please fix the road in our barangay please"), False)
    check("different is not near",
          is_near_duplicate("please fix the road in our barangay",
                            "salamat sa mga doctor mabuting trabaho"), False)
    check("short substring is not near",
          is_near_duplicate("fix it", "fix it now and also the other thing"), False)

    # ---- dedupe_dataset ----
    rows = [
        {"comment_id": "a", "dedup_key": "x y", "comment_text_norm": "x y",
         "source_page": "p", "post_id": "po1", "collected_at": "2026-10-20T01:00:00Z"},
        {"comment_id": "b", "dedup_key": "x y", "comment_text_norm": "x y",
         "source_page": "p", "post_id": "po1", "collected_at": "2026-10-20T02:00:00Z"},
        {"comment_id": "c", "dedup_key": "q r", "comment_text_norm": "q r",
         "source_page": "p", "post_id": "po1", "collected_at": "2026-10-20T03:00:00Z"},
    ]
    kept, removed = dedupe_dataset(rows)
    check("dedup keeps 2", len(kept), 2)
    check("dedup removes 1", len(removed), 1)
    check("dedup reason", removed[0].get("_reason"), "X_DUP_EXACT")
    check("dedup keeps earliest", kept[0]["comment_id"], "a")

    # a post may contribute many UNRELATED comments (the near-dup cap must not
    # truncate the dataset)
    many = [
        {"comment_id": f"m{i}", "dedup_key": f"k{i}", "comment_text_norm": f"unique text {i}",
         "source_page": "p", "post_id": "po9", "collected_at": f"2026-10-20T{i:02d}:00:00Z"}
        for i in range(10)
    ]
    kept2, removed2 = dedupe_dataset(many)
    check("10 unrelated comments all kept", len(kept2), 10)
    check("none removed", len(removed2), 0)

    # ---- spam (contract 8) ----
    check("repeated token detected", is_repeated_token("hahahahahahaha"), True)
    check("repeated token HAHA", is_repeated_token("HAHA"), True)
    check("real word not repeated token", is_repeated_token("mama"), False)
    srows = [
        {"comment_id": "s1", "comment_text_norm": "Job hiring! click here https://x.com/a",
         "comment_text": "Job hiring! click here https://x.com/a",
         "source_page": "p", "post_id": "po1"},
        {"comment_id": "s2", "comment_text_norm": "hahahahahahaha",
         "comment_text": "hahahahahahaha", "source_page": "p", "post_id": "po1"},
        {"comment_id": "s3", "comment_text_norm": "Please fix the road in our barangay",
         "comment_text": "Please fix the road in our barangay",
         "source_page": "p", "post_id": "po1"},
        {"comment_id": "s4", "comment_text_norm": "add me on fb for more promos",
         "comment_text": "add me on fb for more promos", "source_page": "p", "post_id": "po1"},
    ]
    kept, rem = filter_spam(srows)
    check("spam kept 1", len(kept), 1)
    check("spam kept the good one", kept[0]["comment_id"], "s3")
    check("spam removed 3", len(rem), 3)
    check("spam reasons", {r["_reason"] for r in rem}, {"X_SPAM"})

    # ---- pii (contract 11) ----
    txt, mod, hits = scrub_text("si Juan ay nagtanong, call 09171234567 or j@d.gov.ph")
    check("pii modified", mod, True)
    check("pii name", "<NAME>" in txt, True)
    check("pii phone", "<PHONE>" in txt, True)
    check("pii email", "<EMAIL>" in txt, True)
    txt2, mod2, _ = scrub_text("Please fix the road in our barangay")
    check("clean text untouched", (mod2, txt2), (False, "Please fix the road in our barangay"))

    # ---- pipeline end to end ----
    pool = [
        {"comment_id": "p1", "comment_text": "Please repair the damaged road in our barangay.",
         "post_text": "Baha sa amin", "parent_comment_text": "", "source_page": "pagasa",
         "post_id": "po1", "collected_at": "2026-10-20T01:00:00Z"},
        {"comment_id": "p2", "comment_text": "Please repair the damaged road in our barangay.",
         "post_text": "Baha sa amin", "parent_comment_text": "", "source_page": "pagasa",
         "post_id": "po1", "collected_at": "2026-10-20T02:00:00Z"},
        {"comment_id": "p3", "comment_text": "Job hiring! click here https://x.com/a",
         "post_text": "Baha sa amin", "parent_comment_text": "", "source_page": "pagasa",
         "post_id": "po1", "collected_at": "2026-10-20T03:00:00Z"},
        {"comment_id": "p4", "comment_text": "",
         "post_text": "Baha sa amin", "parent_comment_text": "", "source_page": "pagasa",
         "post_id": "po1", "collected_at": "2026-10-20T04:00:00Z"},
        {"comment_id": "p5", "comment_text": "Salamat sa mga doctor!",
         "post_text": "Baha sa amin", "parent_comment_text": "", "source_page": "pagasa",
         "post_id": "po1", "collected_at": "2026-10-20T05:00:00Z"},
    ]
    kept, ledger = clean(pool)
    counts = ledger_counts(ledger)
    check("pipeline kept 2", len(kept), 2)
    check("pipeline removed 3", len(ledger), 3)
    check("pipeline reconciles", len(kept) + len(ledger), len(pool))
    check("X_DUP_EXACT counted", counts.get("X_DUP_EXACT"), 1)
    check("X_SPAM counted", counts.get("X_SPAM"), 1)
    check("X_EMPTY counted", counts.get("X_EMPTY"), 1)
    check("normalized", kept[0]["comment_text_norm"],
          "Please repair the damaged road in our barangay.")
    check("context built", kept[0]["context_text_norm"], "[POST] Baha sa amin")
    check("dedup key built", kept[0]["dedup_key"],
          "please repair the damaged road in our barangay")

    return failures
