"""
dedup.py — exact and near duplicate removal.

Implements DATA_CONTRACT.md 7. Exact duplicates are keyed on `dedup_key`.
Near duplicates are a substring relation with a minimum token length, or a
token Jaccard similarity at or above 0.90.

Both rules run BEFORE the train/dev/test split. If a duplicate pair straddles
the split, the model is evaluated on text it has already seen.

Two different retention rules, and the difference matters:

  exact  - keep the EARLIEST captured (contract 7.1)
  near   - keep the LONGER, because it carries more information (contract 7.2)

The near-duplicate cap is a cap on how many NEAR-IDENTICAL comments survive
from the same account on the same post. It is not a cap on how many comments
a post may contribute. An earlier draft got that wrong and would have
truncated the dataset to two comments per post.

Removal is recorded with a reason code so the exclusion ledger reconciles.
"""

from __future__ import annotations

from .normalize import token_count, token_set

# Contract 7.2
JACCARD_THRESHOLD = 0.90
SUBSTRING_MIN_TOKENS = 5

# Contract 7.2 - retained near-identical comments per (account, post)
NEAR_CAP = 2

REASON_EXACT = "X_DUP_EXACT"
REASON_NEAR = "X_DUP_NEAR"


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def is_near_duplicate(a: str, b: str) -> bool:
    """Contract 7.2. One is a substring of the other (shorter >= 5 tokens),
    or token Jaccard >= 0.90."""
    if not a or not b:
        return False

    ta, tb = token_count(a), token_count(b)
    shorter, longer = (a, b) if ta <= tb else (b, a)

    # substring relation, only when the shorter side has enough tokens
    if token_count(shorter) >= SUBSTRING_MIN_TOKENS and shorter in longer:
        return True

    return jaccard(token_set(a), token_set(b)) >= JACCARD_THRESHOLD


def dedupe(rows: list, key_field: str = "dedup_key", text_field: str = "comment_text_norm",
           group_field: str = "source_page", post_field: str = "post_id") -> tuple:
    """Remove exact and near duplicates.

    Returns (kept_rows, removed_rows). Each removed row carries a `_reason`
    key holding the reason code, and `_dup_of` naming the row it lost to.
    """
    kept = []
    removed = []
    seen_exact = {}                       # dedup_key -> kept row
    group_rows = {}                       # (group, post) -> list of kept rows

    # earliest captured first, so "keep the earliest" falls out of the iteration
    ordered = sorted(rows, key=lambda r: (r.get("collected_at", ""), r.get("comment_id", "")))

    for row in ordered:
        key = (row.get(key_field) or "").strip()
        text = row.get(text_field) or ""
        group = (row.get(group_field, ""), row.get(post_field, ""))
        bucket = group_rows.setdefault(group, [])

        # ---------- exact duplicate: keep the earliest ----------
        if key and key in seen_exact:
            dup = dict(row)
            dup["_reason"] = REASON_EXACT
            dup["_dup_of"] = seen_exact[key].get("comment_id", "")
            removed.append(dup)
            continue

        # ---------- near duplicate: keep the longer ----------
        near = [other for other in bucket
                if is_near_duplicate(text, other.get(text_field) or "")]

        if near:
            # how many KEPT rows in this group are near-identical to this one
            if len(near) >= NEAR_CAP:
                dup = dict(row)
                dup["_reason"] = REASON_NEAR
                dup["_dup_of"] = near[0].get("comment_id", "")
                removed.append(dup)
                continue

            # the new row may be more informative than the ones it duplicates
            longest = max(near, key=lambda o: token_count(o.get(text_field) or ""))
            if token_count(text) > token_count(longest.get(text_field) or ""):
                # the new row wins: the previously kept one is demoted
                kept.remove(longest)
                bucket.remove(longest)
                demoted = dict(longest)
                demoted["_reason"] = REASON_NEAR
                demoted["_dup_of"] = row.get("comment_id", "")
                removed.append(demoted)

        kept.append(row)
        bucket.append(row)
        if key:
            seen_exact[key] = row

    return kept, removed


def dedupe_dataset(rows: list) -> tuple:
    """Convenience wrapper using the contract's column names."""
    return dedupe(rows, key_field="dedup_key", text_field="comment_text_norm",
                  group_field="source_page", post_field="post_id")
