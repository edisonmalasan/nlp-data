# `data/` — dataset layers

Read `DATA_CONTRACT.md` §13 before adding anything here. Each layer has a different
access rule and a different commit rule.

| Path | Contains | Committed to git? | Release-ready? |
|---|---|---|---|
| `raw/` | Immutable platform payloads, exactly as retrieved. Never edited. | **No** | No |
| `interim/` | Verbatim union of raw, pre-cleaning. Not yet scrubbed. | **No** | No |
| `processed/` | The delivered dataset: cleaned, deduped, anonymized, labeled. | **Yes** | Yes |
| `provenance/` | Source account list and collection log. | **Yes** | Yes |

## Key files

| File | Grain | Notes |
|---|---|---|
| `processed/dataset_v1.csv` | one row per usable comment | **Primary dataset — Facebook only.** Matches the paper title/abstract exactly. |
| `processed/dataset_v1_ext.csv` | one row per usable comment | Extended dataset — all platforms. `dataset_v1` is exactly the subset where `platform == "facebook"`. |
| `processed/posts_v1.csv` | one row per source post | Post context master. Denormalized post fields in the comment files must match this byte-for-byte (check V-07). |
| `processed/splits/{train,dev,test}.csv` | one row per comment | **Authoritative** split assignment. Join on `comment_id`. |
| `processed/dataset_v1.metadata.json` | — | Counts, provenance, versions, agreement stats. Populated at G3. |
| `interim/comments_captured.csv` | one row per captured comment | Pre-cleaning. Internal only. |
| `provenance/government_agencies.csv` | one row per source account | Frozen at G1. |
| `provenance/collection_log.csv` | one row per collection run | Audit trail for each retrieval run. |

## Rules

1. **Never** hand-edit `processed/*.csv`. Regenerate from `raw/` via `src/clean/`.
2. **Never** commit anything from `raw/` or `interim/` — excluded by `.gitignore`.
3. **Never** change a label, a split, or a `comment_id` silently. New version, new file,
   changelog entry (§17 of the contract).
4. The split files win over the `split` column if they ever disagree — and if they ever
   do, that is a bug to report immediately (`tools/validate_dataset.py` check V-10).

## Label encoding

`label = 1` → actionable suggestion/request · `label = 0` → other comment.

If you are loading this for modeling, use `pos_label=1`. A flipped `pos_label` inverts
every metric and silently invalidates the paper's conclusion.

## What the model development stage loads

The final deliverable is the **`processed/` layer**: the labeled dataset plus the split
files. `splits/*.csv` are **authoritative** — the `split` column inside `dataset_v1.csv` is
only a convenience mirror.

```python
import pandas as pd

ds = pd.read_csv("data/processed/dataset_v1.csv")
splits = pd.concat([
    pd.read_csv(f"data/processed/splits/{s}.csv") for s in ("train", "dev", "test")
], ignore_index=True)

df = ds.merge(splits[["comment_id", "split"]], on="comment_id",
              how="inner", validate="one_to_one")

tr = df[df.split == "train"]
dv = df[df.split == "dev"]
te = df[df.split == "test"]

X_tr, y_tr = tr["comment_text_norm"], tr["label"]
X_dv, y_dv = dv["comment_text_norm"], dv["label"]
X_te, y_te = te["comment_text_norm"], te["label"]
```

Three rules that make the comparison valid:

1. **Both models use the same `X_te` / `y_te`.** The baseline and the feature-augmented
   model must be scored on one identical held-out test set — that is the whole basis of the
   comparison.
2. **The text field is `comment_text_norm` only.** Do not concatenate `post_text` or
   `context_text_norm` into the primary feature space; that would add a third, unreported
   variable. `context_text_norm` exists for a separately-labelled robustness analysis.
3. **`pos_label=1` on every metric call.**

```python
from sklearn.metrics import classification_report, f1_score, confusion_matrix

print(classification_report(y_te, pred, pos_label=1, zero_division=0))
print(f1_score(y_te, pred, pos_label=1))
print(confusion_matrix(y_te, pred, labels=[0, 1]))   # [[TN, FP], [FN, TP]]
```

Also available: `processed/posts_v1.csv` for post context (join on `post_id`), and
`processed/dataset_v1.metadata.json` for the row counts, class distribution, per-agency
counts, provenance and agreement statistics that accompany the release.

