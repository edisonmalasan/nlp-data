"""
pipeline.py — the Stage 2 cleaning pipeline.

Runs the full cleaning chain over a candidate pool and produces the
interim rows, the cleaned pool, and the exclusion ledger.

Order (DATA_CONTRACT.md 5.6, stage 2):
    extract -> filter -> normalize -> dedup -> scrub

Dedup runs before the split, always. Every removal is counted with a reason
code so the ledger reconciles against the metadata's `lineage` block.
"""

from __future__ import annotations

import csv
import io
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from clean.normalize import build_context, dedup_key, normalize_text, token_count
from clean.dedup import dedupe_dataset
from clean.spam import filter_spam
from clean.pii import scrub_rows

# Reason codes (contract 4.2)
REASONS = [
    "X_SRC", "X_OFFICIAL", "X_LANG", "X_EMPTY",
    "X_DUP_EXACT", "X_DUP_NEAR", "X_SPAM", "X_PII",
    "X_DELETED", "X_UNREADABLE",
]


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


def is_other_language(text: str) -> bool:
    """Contract 4.2, X_LANG. A crude script check: text that is neither
    Filipino/English-ish. The collector filters at collection time too, so
    this is a backstop, not the primary filter."""
    if not text:
        return False
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    ascii_letters = sum(1 for c in letters if ord(c) < 128)
    return ascii_letters / len(letters) < 0.5


def clean(rows: list) -> tuple:
    """Run the cleaning chain. Returns (kept, ledger).

    `ledger` is a list of removed rows, each with `_reason`.
    """
    ledger = []

    # ---------- stage 2b: per-row exclusion rules ----------
    survivors = []
    for row in rows:
        text = (row.get("comment_text") or "").strip()
        reason = None

        if not text:
            reason = "X_EMPTY"
        elif (row.get("author_is_official") or "").lower() == "true":
            reason = "X_OFFICIAL"
        elif is_other_language(text):
            reason = "X_LANG"

        if reason:
            dup = dict(row)
            dup["_reason"] = reason
            ledger.append(dup)
        else:
            survivors.append(row)

    # ---------- stage 2c: normalize ----------
    # Build a new list rather than mutating `survivors` while iterating it:
    # removing inside the loop skips the next element.
    normalized = []
    for row in survivors:
        raw = row.get("comment_text") or ""
        norm = normalize_text(raw)
        row["comment_text_norm"] = norm
        row["dedup_key"] = dedup_key(norm)
        row["n_tokens"] = token_count(norm)
        row["context_text_norm"] = build_context(
            row.get("post_text", ""), row.get("parent_comment_text", "")
        )
        if not norm:
            dup = dict(row)
            dup["_reason"] = "X_EMPTY"
            ledger.append(dup)
        else:
            normalized.append(row)
    survivors = normalized

    # ---------- stage 2d: dedup (BEFORE spam, per contract 5.6) ----------
    # Order matters. If spam runs first, rule F6 (account posting near-identical
    # text) fires on exact duplicates and mislabels them X_SPAM instead of
    # X_DUP_EXACT, which corrupts the exclusion ledger.
    survivors, dup_removed = dedupe_dataset(survivors)
    ledger.extend(dup_removed)

    # ---------- stage 2b: spam ----------
    survivors, spam_removed = filter_spam(survivors)
    ledger.extend(spam_removed)

    # ---------- stage 2e: PII scrub ----------
    survivors, pii_removed = scrub_rows(survivors)
    ledger.extend(pii_removed)

    return survivors, ledger


def ledger_counts(ledger: list) -> dict:
    c = Counter(r.get("_reason", "X_UNREADABLE") for r in ledger)
    return {k: c.get(k, 0) for k in REASONS if c.get(k, 0)}


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Stage 2 - clean the candidate pool")
    ap.add_argument("--pool", required=True, help="interim pool (verbatim rows)")
    ap.add_argument("--out", required=True, help="cleaned pool output (csv)")
    ap.add_argument("--ledger-out", required=True, help="exclusion ledger (csv)")
    ap.add_argument("--report", default=None, help="optional json report path")
    args = ap.parse_args(argv)

    rows = load_rows(args.pool)
    print(f"loaded {len(rows)} rows from {args.pool}")

    kept, ledger = clean(rows)
    counts = ledger_counts(ledger)

    fieldnames = list(rows[0].keys()) if rows else []
    for extra in ("comment_text_norm", "context_text_norm", "dedup_key",
                  "n_tokens", "pii_redacted"):
        if extra not in fieldnames:
            fieldnames.append(extra)
    write_rows(args.out, kept, fieldnames)
    write_rows(args.ledger_out, ledger, fieldnames + ["_reason"])

    print(f"kept {len(kept)} rows -> {args.out}")
    print(f"removed {len(ledger)} rows -> {args.ledger_out}")
    for reason, n in sorted(counts.items()):
        print(f"   {reason:14} {n}")

    # reconciliation
    total = len(rows)
    accounted = len(kept) + sum(counts.values())
    if total == accounted:
        print("reconciliation OK: kept + excluded == loaded")
    else:
        print(f"RECONCILIATION FAILED: {total} != {accounted}")
        return 1

    if args.report:
        import json
        with io.open(args.report, "w", encoding="utf-8") as fh:
            json.dump({"n_loaded": total, "n_kept": len(kept),
                       "n_excluded": len(ledger), "excluded_by_reason": counts},
                      fh, indent=2)

    return 0


if __name__ == "__main__":
    sys.exit(main())
