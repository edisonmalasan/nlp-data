# `data/final/` — the release package

This is the **single artifact the modeling stage receives**. Everything the model
development stage needs is here, and nothing else is.

Build it with:

```bash
python tools/build_release.py --check          # is it ready?
python tools/build_release.py --build          # assemble the package
python tools/build_release.py --build --zip    # and zip it
```

When it is done, `data/final/` contains a folder you can compress and hand over as-is.

---

## What lands here

| File | What it is |
|---|---|
| `dataset_v1.csv` | **The dataset.** One row per usable comment, 39 columns, labeled. Facebook-only — matches the study's framing. |
| `dataset_v1_ext.csv` | The same schema across all platforms. Optional extension. |
| `posts_v1.csv` | Post context master. Join on `post_id`. |
| `train.csv` · `dev.csv` · `test.csv` | **Authoritative** split assignment. Join on `comment_id`. |
| `dataset_v1.metadata.json` | Counts, class distribution, per-agency counts, provenance, reliability, lineage. |
| `government_agencies.csv` | Which Philippine government agency each row came from. |
| `ANNOTATION_GUIDELINES.md` | The rules the labels were produced under. |
| `README.md` | This file. |
| `MANIFEST.json` | Build timestamp, row counts, and a SHA-256 for every file above. |
| `nlp-actionable-comments-v1.zip` | The archive, if you built with `--zip`. |

---

## How to load it

```python
import pandas as pd

ds = pd.read_csv("data/final/dataset_v1.csv")
splits = pd.concat(
    [pd.read_csv(f"data/final/{s}.csv") for s in ("train", "dev", "test")],
    ignore_index=True,
)

df = ds.merge(splits[["comment_id", "split"]], on="comment_id",
              how="inner", validate="one_to_one")

tr = df[df.split == "train"]
dv = df[df.split == "dev"]
te = df[df.split == "test"]

X_tr, y_tr = tr["comment_text_norm"], tr["label"]
X_dv, y_dv = dv["comment_text_norm"], dv["label"]
X_te, y_te = te["comment_text_norm"], te["label"]
```

---

## The three rules

1. **Both models score the same `test.csv`.** One identical held-out test set — that is
   the entire basis of the comparison.
2. **The text field is `comment_text_norm` only.** Do not concatenate `post_text` or
   `context_text_norm` into the feature space; that would add a third, unreported
   variable. `context_text_norm` is there for a separately-labelled robustness analysis.
3. **`pos_label=1` on every metric call.** Flipped, every number inverts.

```python
from sklearn.metrics import classification_report, f1_score, confusion_matrix

print(classification_report(y_te, pred, pos_label=1, zero_division=0))
print(f1_score(y_te, pred, pos_label=1))
print(confusion_matrix(y_te, pred, labels=[0, 1]))   # [[TN, FP], [FN, TP]]
```

---

## Columns worth knowing

| Column | Notes |
|---|---|
| `label` | `1` = actionable, `0` = other. The target. |
| `label_str` | Human-readable mirror of `label`. |
| `comment_text` | Verbatim, original casing, emoji, typos preserved. |
| `comment_text_norm` | Lightly normalized. **This is the modeling field.** |
| `context_text_norm` | Post + parent comment context. Annotation aid and robustness analysis only. |
| `agency_id` → `government_agencies.csv` | The Philippine government entity the row came from. |
| `language` | `fil` / `eng` / `mixed`. |
| `verification` | How the label was produced: `auto`, `human_verified`, or `human_labeled`. |
| `annotation_rule` | The rule that produced the label, e.g. `request_marker + action_verb`. |
| `annotation_evidence` | The cues that fired, or the adjudicator's note. |
| `annotation_confidence` | Engine confidence (`1.0` for adjudicated rows). |
| `label_2`, `agreement` | The blinded re-label reading and whether the two passes matched. |
| `guideline_version` | The ruleset the label was produced under. |
| `split` | Mirror of the split files. The files are authoritative. |

---

## Before you release

- [ ] `python tools/validate_dataset.py` → **0 errors**
- [ ] `python tools/build_release.py --check` → **READY TO RELEASE**
- [ ] The row-count reconciliation holds:
      `n_raw_captured = n_candidate_pool + Σ exclusions = n_labeled = n_usable_final = train+dev+test`
- [ ] Reliability κ ≥ 0.60 on the re-labeled subset
- [ ] Human-verified sample ≥ 100 rows, and the rate is recorded in the metadata
- [ ] The usable-comment count is recorded — it fills the `<number>` placeholder in the
      study's Scope section
