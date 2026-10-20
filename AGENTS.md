# AGENTS.md — operating rules for this repository

Instructions for an AI agent (or a new teammate) working on this codebase. Read this
before changing anything. For orientation, see `CONTEXT.md`; for the binding spec, see
`DATA_CONTRACT.md`.

---

## 1. What this repository is for

**Data collection, scraping, and annotation** for the study *"Detecting Actionable
Suggestions in Filipino-English Code-Switched Government Social Media Comments."*

You are the **producer** of a labeled dataset. Another team builds the model from it. Your
job ends when the release package is built and validated.

**Out of scope — do not do these here:** sentiment labels, model training, feature
engineering, hyperparameter tuning, evaluation metrics, or writing the paper's results and
conclusion. If asked for any of them, point to the modeling stage.

---

## 2. The repository map

```
CONTEXT.md              ← orientation: stages, files, schema, thresholds
DATA_CONTRACT.md        ← binding: schema, rules, splits, validation, compliance
AGENTS.md               ← this file
docs/
  STAGES.md             ← the six stages, as a checklist with exit criteria
  ANNOTATION_GUIDELINES.md  ← the labeling rules and example bank
  NLP-PLAN.pdf          ← source: task assignment
  NLP-Final-Paper.pdf   ← source: scope, objectives, label definitions
data/
  raw/       [gitignored]  immutable platform payloads
  interim/   [gitignored]  pre-cleaning rows + annotator scoring output
  processed/ [committed]   the working dataset, splits, metadata
  final/     [committed]   the release package  ← what the modeling stage receives
  provenance/[committed]   source registry + collection log
src/
  annotate/auto_annotator.py   the annotator engine
  collect/orca_fb.py           the primary collector (orca computer-use)
  collect/alt_text.py          strips generated image descriptions
  collect/facebook.py          the scripted fallback scraper
  collect/to_interim.py        raw capture -> interim CSV
  clean/                       normalize, dedup, spam, pii, pipeline
tools/
  validate_dataset.py          acceptance test V-01..V-17
  split_dataset.py             70/15/15, grouped by post_id, seed 42
  build_release.py             assembles data/final/ + zip
tests/
  run_all.py                   the test suite
  fb_fixture.html              a saved page for the extractor tests
```

---

## 3. Non-negotiable rules

Violating any of these silently invalidates the study. There is no partial credit.

### 3.1 `label = 1` means actionable. Always use `pos_label=1`.

```python
classification_report(y, pred, pos_label=1, zero_division=0)
f1_score(y, pred, pos_label=1)
confusion_matrix(y, pred, labels=[0, 1])   # [[TN, FP], [FN, TP]]
```

A flipped `pos_label` inverts every metric and invalidates the paper's conclusion.

### 3.2 Never define a label by politeness markers.

`please`, `dapat`, `sana`, `paki-` are **evidence**, not the definition. A comment is
actionable only if it identifies a concrete action the agency could take.

*Why this is a hard rule:* the research question asks whether adding these markers as
**features** improves detection. If labels were marker-based, the answer would be trivially
yes and the study would measure nothing. The annotator engine enforces it — a marker only
counts alongside an action verb, a strong request frame, or an action object.

**Never add a politeness marker to `ACTION_VERBS` in `auto_annotator.py`.** `maayos ang`
was removed for exactly this reason — "the road is fixed" is a state, not an action.

### 3.3 The modeling text field is `comment_text_norm` only.

Never concatenate `post_text` or `context_text_norm` into the feature space for the primary
models. That injects a third, unreported variable. Context is for annotation and for a
separately-labelled robustness analysis.

### 3.4 Both models score the same `test.csv`.

One identical held-out test set is the entire basis of the comparison. The split **files**
are authoritative; the `split` column in `dataset_v1.csv` is a mirror. If they ever
disagree, the files win and it is a bug to fix immediately.

### 3.5 Never hand-edit `data/processed/*.csv`.

Regenerate from `data/raw/` via `src/clean/`. The processed layer is an output, not a
source.

### 3.6 Never commit `data/raw/` or `data/interim/`.

Raw payloads are immutable and may be large. Interim rows are pre-scrub. Both are
gitignored. Only `data/processed/`, `data/final/`, `data/provenance/` and the docs are
tracked.

### 3.7 Never silently change a label, a split, or a `comment_id`.

New version, new file, changelog entry (`DATA_CONTRACT.md` §17). `comment_id`s are never
reused or renumbered.

### 3.8 Never weaken a validation check to make it pass.

Fix the underlying problem. If a check is genuinely wrong, change it in `DATA_CONTRACT.md`
§14 with a changelog entry, not in the code.

---

## 4. Working rules

### 4.1 Schema changes are contract changes

The dataset schema is defined in `DATA_CONTRACT.md` §5.2 and is currently **39 columns**.
To add, remove, rename, or reorder a column:

1. Update the §5.2 table (renumber contiguously).
2. Update the header of `data/processed/dataset_v1.csv` **and** `dataset_v1_ext.csv` to
   match, in the same order.
3. Update any code that writes those columns (`src/annotate/auto_annotator.py` writes
   only the contract columns).
4. Bump the contract version and add a changelog row.

The contract table and the CSV header must always match exactly. Verify before committing.

### 4.2 `apply` must write only the contract columns

`auto_annotator.py apply` drops the scoring scratch columns (`confidence`, `rule`,
`evidence`, `cues`) and maps them onto the contract's `annotation_rule`,
`annotation_evidence` and `annotation_confidence` instead. Keep it that way.

### 4.3 Every excluded row leaves a trail

Cleaning exclusions get a reason code (`X_DUP_EXACT`, `X_DUP_NEAR`, `X_SPAM`, `X_LANG`,
`X_EMPTY`, `X_OFFICIAL`, `X_PII`) and the counts go into the metadata's `lineage` block.
Silent drops are not acceptable.

### 4.4 The line-count reconciliation must hold

```
n_raw_captured = n_extracted_to_interim = n_candidate_pool + Σ(n_excluded_by_reason.values())
n_candidate_pool = n_labeled = n_usable_final = train + dev + test
```

If a row cannot be accounted for, that is a bug, not a rounding difference.

### 4.5 Deduplicate before splitting

Exact (`dedup_key`) and near (token Jaccard ≥ 0.90) duplicates are removed **before** the
train/dev/test split. Otherwise the model is tested on text it has already seen.

### 4.6 Split grouped by `post_id`

The same post's comments never straddle two splits. Otherwise the model is scored on its
own vocabulary.

### 4.7 The cleaning order is fixed

    filter → normalize → dedup → spam → scrub

Deduplication runs **before** the spam filters. If spam runs first, rule F6 (an account
posting near-identical text) fires on exact duplicates and mislabels them `X_SPAM`
instead of `X_DUP_EXACT`, which corrupts the exclusion ledger.

### 4.8 The near-duplicate cap is a cap on near-identical rows

Contract 7.2 caps how many **near-identical** comments survive from the same account on
the same post at 2. It is **not** a cap on how many comments a post may contribute. A post
with 40 unrelated comments keeps all 40.

### 4.9 Scrub, don't filter

Never remove a row because of its sentiment, profanity, political content, or length
(beyond empty text). Aggressive filtering is the fastest way to silently lose the negative
and non-actionable classes.

---

## 5. The annotator engine

`src/annotate/auto_annotator.py` — read `src/annotate/README.md` before changing it.

### 5.1 The three stages

1. **Cue extraction** — request markers, action verbs, strong request frames, action
   objects, complaint markers, gratitude, reaction, information questions, refusals.
2. **Heuristic scoring** — suggested label + confidence + the rule that fired.
3. **Adjudication** — every row below **0.85** is exported for a decision, plus a **random
   10% audit sample** of the rows it could decide (seed `42`).

### 5.2 The disputed class is never auto-decided

`request_marker + object_only` (e.g. *"Sana maayos ang kalsada"*) scores **0.60** and always
routes to adjudication, because it is the most common disagreement in the guidelines
(§5.3 #35 vs #36). Do not raise that threshold to make the engine do more work.

### 5.3 Tuning the cue lists

The cue lists are recall-oriented on purpose: a cue that fires wrongly costs one
adjudication, but a cue that never fires means a request is silently missed.

- Keep `REQUEST_MARKERS` as evidence only.
- Keep `STRONG_REQUEST_FRAMES` small and frame-like. `dapat`, `kailangan`, `need to` imply
  an action on their own; `sana` does not and belongs in `REQUEST_MARKERS`.
- After any change, re-check the disputed examples in guidelines §5.3 still route to
  adjudication rather than being auto-decided.

### 5.4 Every row ends up with a decision

Rows still below threshold after the merge are reported as a warning and **block release**.

### 5.5 Human verification is required

≥ 100 random rows reviewed without seeing the engine's label, with the agreement rate and
κ recorded. If the engine disagrees on more than ~20% of the sample, **fix the cue lists
before releasing**. Do not release a dataset whose annotator is that far off.

---

## 6. How the annotation must be described

**This is the one thing in this file that is not negotiable.**

The study used **LLM-assisted annotation with human verification**. It did **not** use
manual annotation by a human researcher.

- Do **not** describe the labeling as manual annotation. The assigned task said
  "manually annotate"; if the write-up says 1,000 comments were hand-labeled when the
  engine did it, that is a misreport.
- The write-up must state: the engine and its version, the cue/rule design, the share of
  rows auto-decided vs adjudicated vs human-verified, the human-verification sample size
  and agreement, and the blinded re-label κ.
- The reliability statistic is **intra-annotator reliability** (test-retest), not
  inter-annotator agreement. There is one annotator.

---

## 7. Before you commit

- [ ] The contract's §5.2 table and the CSV headers still match, column for column, in
      order.
- [ ] `python tests/run_all.py` passes.
- [ ] `python src/annotate/auto_annotator.py score` and `apply` still run end to end.
- [ ] The annotator unit expectations still pass, and the disputed examples still route to
      adjudication.
- [ ] `python tools/build_release.py --check` behaves correctly.
- [ ] No file under `data/raw/` or `data/interim/` is staged.
- [ ] No new rule was introduced that is not written in `DATA_CONTRACT.md`.
- [ ] If you changed the schema, the contract version is bumped and the changelog has a
      row.
- [ ] Commit message describes the *why*, in the imperative mood.

---

## 8. Commit conventions

Conventional Commits. One logical change per commit.

```
feat(annotate): add cue extraction for strong request frames
fix(release): preserve data/final/README.md when rebuilding the package
docs(stages): correct the stage 5 column count
chore(collect): scaffold the Facebook scraper
```

Branch names: `feat/...`, `fix/...`, `docs/...`, `chore/...` with a short hyphenated
description.

---

## 9. Quick reference

| I need to… | Command / file |
|---|---|
| Know what to do next | `docs/STAGES.md` |
| Run the tests | `python tests/run_all.py` |
| Look up a column | `DATA_CONTRACT.md` §5.2 |
| Label a comment | `docs/ANNOTATION_GUIDELINES.md` §2 and §5 |
| Run the annotator | `src/annotate/README.md` |
| Validate | `python tools/validate_dataset.py` |
| Release | `python tools/build_release.py --build --zip` |
| Know what the modeling stage gets | `data/final/README.md` |
| Find a threshold | `CONTEXT.md` §6 |
