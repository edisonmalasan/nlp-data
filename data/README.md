# `data/` — dataset layers

Read `DATA_CONTRACT.md` §13 before adding anything here. Each layer has a different
access rule and a different commit rule.

| Path | Contains | Committed to git? | Publishable? |
|---|---|---|---|
| `raw/` | Immutable platform payloads, exactly as retrieved. Never edited. | **No** | No |
| `interim/` | Verbatim union of raw, pre-cleaning. May still contain names. | **No** | No |
| `processed/` | The delivered dataset: cleaned, deduped, anonymized, labeled. | **Yes** | Yes, with adviser approval |
| `provenance/` | Source account list and collection audit log. Non-personal. | **Yes** | Yes |

## Key files

| File | Grain | Notes |
|---|---|---|
| `processed/dataset_v1.csv` | one row per usable comment | **Primary dataset — Facebook only.** Matches the paper title/abstract exactly. |
| `processed/dataset_v1_ext.csv` | one row per usable comment | Extended dataset — all platforms. `dataset_v1` is exactly the subset where `platform == "facebook"`. |
| `processed/posts_v1.csv` | one row per source post | Post context master. Denormalized post fields in the comment files must match this byte-for-byte (check V-07). |
| `processed/splits/{train,dev,test}.csv` | one row per comment | **Authoritative** split assignment. Join on `comment_id`. |
| `processed/dataset_v1.metadata.json` | — | Counts, provenance, versions, agreement stats. Populated at G3. |
| `interim/comments_captured.csv` | one row per captured comment | Pre-cleaning. Internal only. |
| `provenance/source_accounts.csv` | one row per source account | Frozen at G1. |
| `provenance/collection_log.csv` | one row per collection run | Audit trail for §12 compliance. |

## Rules

1. **Never** hand-edit `processed/*.csv`. Regenerate from `raw/` via `src/clean/`.
2. **Never** commit anything from `raw/` or `interim/` — raw may contain personal data
   and is excluded by `.gitignore`.
3. **Never** change a label, a split, or a `comment_id` silently. New version, new file,
   changelog entry (§17 of the contract).
4. The split files win over the `split` column if they ever disagree — and if they ever
   do, that is a bug to report immediately (`tools/validate_dataset.py` check V-10).

## Label encoding

`label = 1` → actionable suggestion/request · `label = 0` → other comment.

If you are loading this for modeling, use `pos_label=1`. A flipped `pos_label` inverts
every metric and silently invalidates the paper's conclusion.
