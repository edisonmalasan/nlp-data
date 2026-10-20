# CONTEXT.md — repo mapper

**One place to orient yourself in this repository.** If you read nothing else, read this,
then `DATA_CONTRACT.md` for the binding rules.

| | |
|---|---|
| Project | Detecting Actionable Suggestions in Filipino-English Code-Switched Government Social Media Comments |
| Repository scope | **Data collection, scraping, and annotation only.** Not the model, not the write-up. |
| Institution | Saint Louis University · School of Accountancy, Management, Computing and Information Studies |
| Academic year | 2026–2027 · CSE 30-9712 Special Topics 1 |
| Owner | Member 4 (MALASAN) — the dataset producer |
| Contract version | `1.5-draft` — see `DATA_CONTRACT.md` §17 |
| Dataset schema | **39 columns** — see `DATA_CONTRACT.md` §5.2 |
| Validation | **17 checks**, V-01…V-17 — see `DATA_CONTRACT.md` §14 |

---

## 1. What the study is about

Citizens comment on Philippine government agencies' social media posts. Prior Philippine
work measured **sentiment** (positive/negative/neutral). This study measures **actionability**:

| Comment | Label | Why |
|---|---|---|
| *"Ang pangit ng kalsada namin"* | `0` — other | Complaint with no proposed action |
| *"Please repair the damaged road in our barangay"* | `1` — actionable | Identifies a concrete action |

**Research question.** Does adding suggestion-related linguistic features (`please`, `dapat`,
`sana`, `paki-`) to a TF-IDF + Logistic Regression baseline improve detection of actionable
suggestions in Filipino-English code-switched comments?

**Consequence for everything in this repo:** the label is defined by *whether an action is
identified*, never by whether a politeness marker is present. See §5 below.

---

## 2. The six stages and where each one writes

```
STAGE 0  SELECT SOURCES        data/provenance/government_agencies.csv
              │                docs/COLLECTION_PROTOCOL.md
              ▼
STAGE 1  COLLECT (raw)         data/raw/<platform>/<page>/<run_id>.json
              │                data/provenance/collection_log.csv
              ▼
STAGE 1b EXTRACT               data/interim/comments_captured.csv
              │                data/interim/posts_captured.csv
              ▼
STAGE 2  CLEAN                 data/processed/  ← candidate pool
              │                normalize → dedup → spam → PII scrub
              ▼
STAGE 3  ANNOTATE              data/processed/dataset_v1.csv
              │                src/annotate/auto_annotator.py
              ▼
STAGE 4  SPLIT                 data/processed/splits/{train,dev,test}.csv
              ▼
STAGE 5  VALIDATE & RELEASE    data/processed/validation_report.txt
                               data/final/  ← the hand-off artifact
```

Full step-by-step with checkboxes: **`docs/STAGES.md`**.

---

## 3. File map

### Root

| Path | What it is |
|---|---|
| `README.md` | Orientation. Scope, pipeline, dataset conventions, setup. |
| `DATA_CONTRACT.md` | **The binding document.** Schema, rules, splits, validation, compliance. |
| `CONTEXT.md` | This file — the map. |
| `AGENTS.md` | Operating rules for an AI agent (or a new teammate) working in this repo. |
| `requirements.txt` | Python dependencies. |
| `.gitignore` | Raw and interim layers are excluded; `data/processed/` and `data/final/` are tracked. |

### `docs/`

| Path | What it is |
|---|---|
| `STAGES.md` | The six stages as a checklist with exit criteria. **Start here.** |
| `ANNOTATION_GUIDELINES.md` | The labeling rules, decision tree, 50-example bank, automated workflow. |
| `NLP-PLAN.pdf` | Source: task assignment and proposed research. |
| `NLP-Final-Paper.pdf` | Source: scope, objectives, label definitions, limitations. |
| `COLLECTION_PROTOCOL.md` | The collection procedure, the raw snapshot format, and the pilot plan. |
| `DATA_CARD.md` | Dataset card for the write-up. *(pending — written at Stage 5)* |

### `data/` — the four layers

| Layer | Path | Committed? | Contents |
|---|---|---|---|
| **Raw** | `data/raw/` | **No** | Immutable platform payloads, exactly as returned. Never edited. |
| **Interim** | `data/interim/` | **No** | Verbatim pre-cleaning rows, plus annotator scoring output. |
| **Processed** | `data/processed/` | **Yes** | The working dataset, splits, metadata, validation report. |
| **Final** | `data/final/` | **Yes** (zip excluded) | **The release package** — what Member 5 receives. |
| **Provenance** | `data/provenance/` | **Yes** | Source registry and collection audit log. |

### `data/processed/` — the file inventory

| File | Grain | What it is |
|---|---|---|
| `dataset_v1.csv` | one row per usable comment | **The dataset.** 40 columns, labeled, Facebook-only. |
| `dataset_v1_ext.csv` | one row per usable comment | Same schema across all platforms. Optional extension. |
| `posts_v1.csv` | one row per source post | Post context master. Join on `post_id`. |
| `splits/train.csv` `dev.csv` `test.csv` | one row per comment | **Authoritative** split assignment. Join on `comment_id`. |
| `dataset_v1.metadata.json` | — | Counts, class distribution, per-agency counts, provenance, κ, lineage, verification counts. |
| `validation_report.txt` | — | Output of `tools/validate_dataset.py`. |

### `data/provenance/`

| File | Grain | What it is |
|---|---|---|
| `government_agencies.csv` | one row per (agency, platform) | **The canonical registry.** Pre-filled: 10 agencies, 16 rows, 38 policy domains, official accounts confirmed against each agency's own website. |
| `collection_log.csv` | one row per collection run | Audit trail: tool, user agent, delay, counts, errors. |

### `src/` and `tools/`

| Path | What it is |
|---|---|
| `src/annotate/auto_annotator.py` | **The annotator engine.** Cue extraction → heuristic scoring → adjudication batches → merge. |
| `src/collect/orca_browser.py` | **The primary collector.** Drives Orca's built-in browser for this worktree and reads the page with JavaScript. No focus needed, no credentials. |
| `src/collect/extract_facebook.js` | The DOM extractor that pulls a post and its comment threads out of the page. |
| `src/collect/alt_text.py` | Strips Facebook's generated image descriptions out of captured comments. |
| `src/collect/facebook.py` | The scripted fallback scraper. Headless DOM reader, no credentials. |
| `src/collect/collect_all.py` | **The whole collection.** Facebook → YouTube → X → Reddit → interim → clean, one platform at a time. |
| `src/collect/run_all.py` | One platform, every account. Resumable. |
| `src/collect/discover_links.py` | Reads each agency's Facebook page to find its official X, YouTube and Reddit accounts. |
| `src/collect/to_interim.py` | **The capture hand-off.** Validates a raw snapshot and writes the interim files the cleaning pipeline consumes. |
| `src/annotate/README.md` | How to run the annotation loop, and how to tune the cue lists. |
| `src/collect/` | Platform scrapers. *(pending — Stage 1)* |
| `src/clean/` | **The cleaning package.** `normalize.py`, `dedup.py`, `spam.py`, `pii.py`, `pipeline.py` (the chain + exclusion ledger). |
| `tools/validate_dataset.py` | **The acceptance test**, V-01…V-17. Reads the expected schema from the contract. |
| `tools/split_dataset.py` | **The splitter.** 70/15/15, stratified by label, grouped by `post_id`, seed 42. |
| `tools/build_release.py` | Assembles `data/final/`, writes `MANIFEST.json`, produces the zip. |
| `tests/` | The test suite. `run_all.py` runs every module; `fb_fixture.html` is a saved page for the extractor. |

---

## 4. The dataset schema (40 columns)

| # | Column | Notes |
|---|---|---|
| 1 | `comment_id` | Unique, stable, `<platform>_<source_page>_<seq4>`. Never renumbered. |
| 2–4 | `platform`, `source_page`, `source_page_name` | Where the comment came from. |
| 5–7 | `agency_id`, `agency`, `agency_abbr` | **The Philippine government entity.** `agency_id` is the FK into `government_agencies.csv`. |
| 8–13 | `post_id`, `post_url`, `post_date`, `post_text`, `post_media_type`, `post_topic` | **Post context.** |
| 14–16 | `is_reply`, `parent_comment_id`, `parent_comment_text` | **Thread context.** |
| 17–19 | `comment_text`, `comment_text_norm`, `context_text_norm` | **Text.** `comment_text` is verbatim; `comment_text_norm` is the modeling field. |
| 20–21 | `dedup_key`, `n_tokens` | Dedup and length. |
| 22 | `language` | `fil` / `eng` / `mixed`. |
| 23–24 | `label`, `label_str` | **The target.** `1` = actionable, `0` = other. |
| 25–30 | `annotator_id`, `label_2`, `agreement`, `adjudicated_by`, `adjudication_note`, `guideline_version` | Annotation trace. |
| 31–32 | `source_snapshot`, `collected_at` | Provenance. |
| 33 | `pii_redacted` | Whether the scrub touched the row. |
| 34 | `verification` | `auto` / `human_verified` / `human_labeled`. |
| 35 | `split` | Mirror of the split files. The files are authoritative. |
| 36 | `notes` | Free text. |
| 37–39 | `annotation_rule`, `annotation_evidence`, `annotation_confidence` | **Why each label was assigned.** |

---

## 5. The rules that must not be broken

These four are the ones that silently invalidate the study if violated.

### 5.1 `pos_label=1` everywhere

`label = 1` means actionable. A flipped `pos_label` inverts every reported metric and
invalidates the paper's conclusion.

```python
classification_report(y_te, pred, pos_label=1, zero_division=0)
f1_score(y_te, pred, pos_label=1)
confusion_matrix(y_te, pred, labels=[0, 1])     # [[TN, FP], [FN, TP]]
```

### 5.2 Never define the label by politeness markers

`please` / `dapat` / `sana` / `paki-` are **evidence**, not the definition. Label by whether
an action is identified.

*Why:* the research question asks whether adding these markers as **features** improves
detection. If the label were marker-based, the answer would be trivially yes and the study
would measure nothing. The annotator engine enforces this — a marker only counts alongside
an action.

### 5.3 The modeling text field is `comment_text_norm` only

Do not concatenate `post_text` or `context_text_norm` into the feature space. That would
inject a third, unreported variable. `context_text_norm` exists for a **separately
labelled** robustness analysis.

### 5.4 Both models score the same `test.csv`

One identical held-out test set is the entire basis of the comparison. `splits/*.csv` are
authoritative; the `split` column is only a mirror.

---

## 6. Thresholds and targets — every number in one place

| Thing | Value | Where |
|---|---|---|
| Confidence threshold for auto-deciding a label | `0.85` | `auto_annotator.py` |
| Random audit sample of confident rows | `10%` (seed `42`) | `auto_annotator.py` |
| Blinded re-label pass | `20%` of rows (≥ 200) | guidelines §8.2 |
| Washout before the re-label pass | `≥ 7 days` | guidelines §8.2 |
| Reliability gate (Cohen's κ) | `≥ 0.60` | guidelines §10.1 |
| Human verification sample | `≥ 100` rows, blind | guidelines §8.5 |
| Target usable comments | `≥ 1,000` combined | contract §3.4 |
| Target Facebook-only usable comments | `≥ 600` | contract §3.4 |
| Minimum per class | `≥ 150` | contract §9 |
| Class balance window | `15%`–`65%` actionable | contract §9 |
| Split ratios | `70 / 15 / 15`, seed `42`, grouped by `post_id` | contract §12 |
| Posts per source account | `8`–`12` | contract §3.4 |
| Raw source payload | stored once, never edited | contract §3.3 |

---

## 7. Commands

```bash
pip install -r requirements.txt
playwright install chromium                      # only for the scripted fallback
python tests/run_all.py                         # run the test suite

# Stage 1 - collect (the primary route, through the signed-in browser)
python src/collect/collect_all.py --posts 12

# or a single account
python src/collect/orca_browser.py \
    --account https://www.facebook.com/dswdserves \
    --source-page dswd --agency-id dswd \
    --source-page-name "Department of Social Welfare and Development" \
    --posts 2
python src/collect/to_interim.py \
    --snapshot-dir data/raw/facebook --source-page dswd \
    --platform facebook --agency-id dswd --append

# Stage 3 — annotate
python src/annotate/auto_annotator.py score \
    --pool data/processed/candidate_pool.csv \
    --out data/interim/auto_scored.csv \
    --review-out data/interim/review_batches/
python src/annotate/auto_annotator.py apply \
    --scored data/interim/auto_scored.csv \
    --decisions data/interim/agent_decisions.csv \
    --out data/processed/dataset_v1.csv

# Stage 2 — clean
python src/clean/pipeline.py \\
    --pool       data/interim/comments_captured.csv \\
    --out        data/processed/candidate_pool.csv \\
    --ledger-out data/interim/exclusion_ledger.csv \\
    --report     data/interim/cleaning_report.json

# Stage 4 — split
python tools/split_dataset.py \\
    --dataset data/processed/dataset_v1.csv \\
    --outdir  data/processed/splits \\
    --seed    42

# Stage 5 — validate and release
python tools/validate_dataset.py
python tools/build_release.py --check
python tools/build_release.py --build --zip
```

---

## 8. Where to read next

| If you want to… | Read |
|---|---|
| Do the work, in order | `docs/STAGES.md` |
| Know the exact schema and rules | `DATA_CONTRACT.md` |
| Label a comment | `docs/ANNOTATION_GUIDELINES.md` |
| Run or tune the annotator | `src/annotate/README.md` |
| Know what Member 5 receives | `data/final/README.md` |
| Know what the study claims and doesn't | `docs/NLP-Final-Paper.pdf` |

---

## 9. Glossary

| Term | Meaning |
|---|---|
| **Actionable** | Label `1`. The comment identifies a concrete action for the agency. |
| **Other** | Label `0`. Everything else. |
| **Action object** | The thing that should be changed or fixed. Its presence separates an actionable wish from a general one. |
| **Marker** | A politeness/request word. Evidence, never the definition. |
| **Post context** | The source post's text and metadata, plus the parent comment for replies. Shown to every adjudicator. |
| **Adjudication** | Deciding a row the engine was not sure about, by applying the guidelines. |
| **Blinded re-label pass** | Re-labeling a subset after a washout, without seeing the first answer. The basis of κ. |
| **Gold set** | A fixed, human-checked subset used to measure the engine's accuracy. |
| **Prior** | The natural fraction of actionable comments in collected data, before any balancing. |
| **Mixed / code-switched** | A comment containing both Filipino and English in meaningful proportion. |
| **Lineage** | The row-count chain from raw capture to final dataset. Must reconcile exactly. |
