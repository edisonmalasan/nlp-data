# Release package — actionable-suggestion dataset

**For Member 5 (model development).** This package is final. Do not clean, annotate,
deduplicate, or re-split it. If something looks wrong, raise it with Member 4.

- Study: *Detecting Actionable Suggestions in Filipino-English Code-Switched Government
  Social Media Comments*
- Labels: `1` = actionable suggestion/request, `0` = other
- Schema: 34 columns (`DATA_CONTRACT.md` §5.2). Contract `2.0-draft`, guidelines `v1.0`.
- Primary corpus: **1,657 Facebook comments**, 282 actionable (17.0%), 44 agencies.
- Reliability: Cohen's κ = **0.72** on a 332-row blinded re-label (92.5% agreement);
  κ = **0.79** on a 120-row independent verification sample (93.3% agreement).
  The re-label had no washout, so κ is an upper bound. Verification was
  **model-assisted** (`llm_verified`), not human.

## Files

| File | Rows | What it is | What you use it for |
|---|---:|---|---|
| `dataset_v1.csv` | 1,657 | **Primary dataset.** Facebook only, one row per usable comment, 34 columns, labeled. | Train and evaluate both models. This is the file the paper reports on. |
| `dataset_v1_ext.csv` | 1,828 | Same schema, all platforms (Facebook + YouTube + X). | Optional robustness extension only. Not the headline result. |
| `train.csv` / `dev.csv` / `test.csv` | 1,161 / 248 / 248 | **Authoritative split assignment.** Each row carries `comment_id`, `split`, `platform`, `source_page`, `post_id`, `label`. | Join on `comment_id`. Both models must score the same `test.csv`. |
| `posts_v1.csv` | 212 | Post context master: one row per source post. | Join on `post_id` if you need post text or date. Do not merge `post_text` into the feature space. |
| `dataset_v1.metadata.json` | — | Counts, class balance, per-agency distribution, split counts, lineage, reliability, verification method. | Read the numbers; do not recompute them. |
| `government_agencies.csv` | 62 | Agency registry: `agency_id`, name, abbreviation, account. | Look up which agency a row came from. |
| `ANNOTATION_GUIDELINES.md` | — | The labeling rules the dataset was produced under. | Cite the definition; do not re-label. |
| `MANIFEST.json` | — | Build timestamp and SHA-256 for every file. | Verify integrity. |

## Load it

```python
import pandas as pd

ds = pd.read_csv("dataset_v1.csv")
split = pd.concat([pd.read_csv(f"{s}.csv") for s in ("train", "dev", "test")],
                  ignore_index=True)
df = ds.merge(split[["comment_id", "split"]], on="comment_id",
              how="inner", validate="one_to_one")

train = df[df.split == "train"]
dev   = df[df.split == "dev"]
test  = df[df.split == "test"]

X_train, y_train = train["comment_text_norm"], train["label"]
X_test,  y_test  = test["comment_text_norm"],  test["label"]
```

## Three rules

1. **The modeling text is `comment_text_norm` only.** Never concatenate `post_text` or
   `context_text_norm` into the primary models; that adds a third, unreported variable.
2. **Both models score the same `test.csv`.** The split files are authoritative; the
   `split` column is a mirror.
3. **`pos_label=1` on every metric.** A flipped label invalidates every number.

```python
from sklearn.metrics import classification_report, f1_score, confusion_matrix

print(classification_report(y_test, pred, pos_label=1, zero_division=0))
print(f1_score(y_test, pred, pos_label=1))
print(confusion_matrix(y_test, pred, labels=[0, 1]))   # [[TN, FP], [FN, TP]]
```

## Columns you will touch

| Column | Use |
|---|---|
| `label` | Target: `1` actionable, `0` other. |
| `comment_text_norm` | Primary feature text. |
| `context_text_norm` | Post context only. Annotation aid / optional ablation, not a primary feature. |
| `language` | `fil`, `eng`, or `mixed`. |
| `agency_id` | Agency key. |
| `split` | Mirror of the split files. |
| `label_2`, `agreement` | Second blinded reading and match flag. Available for error analysis. |
| `verification` | `auto` or `llm_verified`. |
| `annotation_rule`, `annotation_evidence`, `annotation_confidence` | Label provenance. |

## What is already done for you

Collection, cleaning, deduplication, PII scrubbing, labeling, adjudication, verification,
splitting, and validation (V-01…V-17, 0 errors). The corpus is **top-level comments
only**; there are no replies. Do not re-collect or re-clean.
