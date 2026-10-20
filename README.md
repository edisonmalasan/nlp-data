# Data Collection, Scraping, and Annotation

**Detecting Actionable Suggestions in Filipino-English Code-Switched Government Social Media Comments**

Saint Louis University · School of Accountancy, Management, Computing and Information Studies
AY 2026–2027 · CSE 30-9712 Special Topics 1

---

## Scope of this repository

This repo covers **one stage only**: the acquisition, cleaning, and annotation of the dataset.

| In scope | Out of scope |
|---|---|
| Selecting eligible government social media accounts | Related literature / research framing |
| Collecting comments through official APIs and manual capture | Model training and hyperparameter tuning |
| Cleaning — dedup, spam removal, PII scrubbing | Feature engineering and evaluation |
| Annotation — labeling, agreement, adjudication | Writing the results and conclusion |
| Split generation and dataset validation | — |

Everything a downstream consumer needs is delivered through **`data/processed/`**, governed by
the schema in [`DATA_CONTRACT.md`](DATA_CONTRACT.md).

**Working path:** [`docs/STAGES.md`](docs/STAGES.md) — the six stages with checkboxes, exit
criteria for each, and the open decisions still blocking you.

---

## Why this data exists

Social media is where Filipino citizens send feedback to government agencies. Prior work on
these comments has mostly measured **sentiment** — positive, negative, neutral. Sentiment does
not tell you **what the citizen wants the government to do**:

> *"Ang pangit ng kalsada namin"* — a complaint.
> *"Please repair the damaged road in our barangay"* — a specific request.

This dataset separates **actionable suggestions and requests** from **other comments** in
Filipino, English, and code-switched public comments on selected Philippine national
government agencies' social media accounts.

### Label taxonomy

| Label | Meaning |
|---|---|
| `1` — **actionable** | The comment proposes an identifiable action, or asks for a specific action or response. |
| `0` — **other** | Everything else. Includes complaints without a proposed action and general wishes without an identifiable action. |

The full task definition, inclusion criteria, and annotation rules live in
[`docs/ANNOTATION_GUIDELINES.md`](docs/ANNOTATION_GUIDELINES.md).

---

## Repository layout

```
nlp-data/
├── README.md                    ← you are here
├── DATA_CONTRACT.md             ← the dataset schema and rules (read first)
├── requirements.txt
├── .gitignore
├── docs/
│   ├── NLP-PLAN.pdf             ← source: task assignment and proposed research
│   ├── NLP-Final-Paper.pdf      ← source: scope, objectives, label definitions
│   ├── ANNOTATION_GUIDELINES.md ← labeling rules, decision tree, example bank
│   ├── STAGES.md               ← the step-by-step path through this scope
│   ├── COLLECTION_PROTOCOL.md   ← (pending) per-source collection detail
│   └── DATA_CARD.md             ← (pending) dataset card for the write-up
├── data/
│   ├── README.md                ← layer rules, label encoding, join instructions
│   ├── raw/                     ← immutable payloads            [not committed]
│   ├── interim/                 ← pre-cleaning verbatim text    [not committed]
│   ├── processed/               ← the delivered dataset         [committed]
│   │   ├── dataset_v1.csv           ← primary: Facebook only
│   │   ├── dataset_v1_ext.csv       ← extended: all platforms
│   │   ├── posts_v1.csv             ← post context master
│   │   ├── dataset_v1.metadata.json ← counts, provenance, versions, κ
│   │   └── splits/{train,dev,test}.csv
│   └── provenance/              ← source accounts + collection log [committed]
│       ├── government_agencies.csv
│       └── collection_log.csv
├── src/
│   ├── collect/                 ← DOM / HTML scrapers (no credentials)
│   ├── clean/                   ← normalize, dedup, spam filter, PII scrub
│   └── annotate/                ← labeling tool setup, agreement computation
└── tools/
    └── validate_dataset.py      ← acceptance test (V-01…V-16)
```

---

## Setup

```bash
git clone https://github.com/edisonmalasan/nlp-data.git
cd nlp-data

python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate

pip install -r requirements.txt
playwright install chromium      # only needed for the Facebook headless scraper
```

**No credentials, keys, tokens, or `.env` file are needed.** There is nothing to configure
before scraping — the collectors read publicly visible pages and nothing else.

| Dependency | Used for |
|---|---|
| `requests` | fetching page HTML and the keyless JSON endpoints |
| `beautifulsoup4` + `lxml` | parsing comment nodes out of the HTML |
| `playwright` | the headless browser for Facebook's client-rendered comment threads |
| `pandas` / `numpy` | the cleaning and annotation tables |
| `scikit-learn` | agreement statistics and later modeling |

**Before any collection begins**, the source list and the collection method must be approved
by the instructor. Record the approval in `docs/COLLECTION_PROTOCOL.md` and log every run in
`data/provenance/collection_log.csv`.

---

## Pipeline

```
        ┌──────────────┐
        │  1. COLLECT  │  read the public HTML/DOM (no keys, no tokens) + manual fallback
        │              │  → data/raw/<platform>/<page>/<run_id>.json   (immutable)
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │   2. CLEAN   │  normalize → dedup (exact + near) → spam filter → PII scrub
        │              │  → data/interim/ → data/processed/  (exclusion ledger logged)
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │  3. ANNOTATE │  guidelines v1.0 → gold set (120, κ≥0.60) → 100% pass
        │              │  → 20% blinded re-label → resolve → labels frozen
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │   4. SPLIT   │  stratified by label, grouped by post_id, seed 42
        │              │  → data/processed/splits/{train,dev,test}.csv
        └──────┬───────┘
               ▼
        ┌──────────────┐
        │  5. VALIDATE │  tools/validate_dataset.py — 16 checks must pass (V-01…V-16)
        │              │  → dataset_v1.metadata.json → hand-off
        └──────────────┘
```

### 1. Collect

Comments are read straight from the **publicly visible HTML/DOM** of each post page.
**No API keys, access tokens, OAuth apps, or account credentials are required** — there is
nothing to sign up for and no `.env` file in this project.

| Platform | How the comments are read | Role |
|---|---|---|
| **Facebook** | Headless browser (Playwright) opens the public permalink, scrolls the thread, reads the rendered DOM | **Primary** — matches the study's framing |
| Facebook (fast path) | `requests` fetch of the permalink, parsing the HTML already in the page source | Shortcut when the comments are server-rendered |
| **YouTube** | `requests` fetch of the watch page, parsing `ytInitialData` and its continuation tokens | Secondary — agency channels have heavy comment volume |
| **Reddit** | Public keyless JSON endpoints (`/comments/<id>.json`) | Optional — sparse, unpredictable yield |
| **X** | Public page HTML / embedded JSON | Optional — least accessible of the four |

**Practical notes**

- **Facebook** renders its comment list client-side, so a plain `requests` fetch often
  returns the post shell with no comments in it. The headless browser that scrolls the
  thread is the reliable route; the raw-HTML path only works when the comments happen to
  be in the page source.
- **YouTube** embeds the first page of comments in `ytInitialData`; the rest come from
  continuation tokens in the same payload.
- **Reddit** needs a descriptive `User-Agent` header or the requests get throttled.
- **Rate behavior:** use a fixed delay between requests and a realistic `User-Agent`.
  Going too fast gets the client IP temporarily blocked, which costs collection time.
  On a block, log it and stop that source for the run instead of retrying in a loop.

### 2. Clean

Deterministic rules, applied in order. Every removed row is **counted and logged with a
reason code** (`X_DUP_EXACT`, `X_DUP_NEAR`, `X_SPAM`, `X_LANG`, `X_PII`, `X_EMPTY`, …).
Silent drops are not acceptable — the counts belong in the write-up.

- **Dedup** — exact (`dedup_key`) and near (token Jaccard ≥ 0.90). Runs **before** the split.
- **Spam** — template bursts, link/promo regexes, repeated-character padding, account-level
  duplicate bursts.
- **PII scrub** — names, @mentions, phone, email, addresses, ID-like digit runs.
- **Never filter on sentiment, profanity, politics, or length** beyond empty-text removal.

### 3. Annotate

Full rules in [`docs/ANNOTATION_GUIDELINES.md`](docs/ANNOTATION_GUIDELINES.md). The short version:

> **Does the comment identify a concrete action the agency could take or the commenter proposes it take?**
> Yes → `actionable` (1). No → `other` (0).

- **Never label by politeness markers.** `please` / `dapat` / `sana` / `paki-` are evidence,
  not the definition. Labeling by marker would make the dataset unable to distinguish a
  text-only model from a marker-aware one.
- **Always read the post context** (post text, date, agency, and parent comment for replies).
  Many replies are unlabelable without it.
- **20% blinded re-label pass** after a ≥ 7 day washout; **Cohen's κ ≥ 0.60** required. This is *intra-annotator* reliability — one annotator, so it is not inter-annotator agreement.
- **Auto-annotation assistant is optional and gated**: macro-F1 ≥ 0.80 **and** κ ≥ 0.60 on a
  120-row self-labeled gold set. Draft labels only, every one human-confirmed, and
  assistant labels excluded from the κ computation.

### 4. Split

70/15/15, stratified by label, **grouped by `post_id`** so the same post's comments never
straddle two splits, seed `42`. Split files are authoritative; join on `comment_id`.

### 5. Validate

`tools/validate_dataset.py` must pass with **0 errors** — 16 checks covering schema, label
encoding, ID uniqueness, agency-registry integrity, post-field consistency, PII leakage,
duplicate leakage, split integrity, class balance, lineage reconciliation, and metadata
completeness.

---

## Data lineage — raw → usable → final

Every comment in the delivered dataset traces back through a fixed chain. **Nothing is ever
deleted or edited in place**; each layer is regenerated from the one above it, and the row
count at every step is recorded.

| # | Stage | Lives in | What happens | Rows |
|---|---|---|---|---|
| 0 | **Capture** | `data/raw/<platform>/<page>/<run_id>.json` | The platform API response, stored **exactly as returned**. Nothing filtered, renamed, or reformatted. | `n_raw_captured` |
| 1 | **Extract** | `data/interim/comments_captured.csv` | Each payload flattened into one row per comment and one row per post. Verbatim text. `agency_id` and `post_id` attached. **No filtering yet.** | `n_extracted_to_interim` |
| 2 | **Clean** | `data/processed/` | Exclusion rules → normalization → dedup → spam filters → PII scrub. Every removal is written to the **exclusion ledger** with a reason code. | `n_candidate_pool` |
| 3 | **Annotate** | `data/processed/dataset_v1.csv` | Labeling under the guidelines. 100% first pass + a 20% blinded re-label pass after a ≥ 7 day washout. | `n_labeled` |
| 4 | **Split** | `data/processed/splits/` | Stratified by label, grouped by `post_id`, seed 42. | train / dev / test |
| 5 | **Validate & freeze** | `dataset_v1.metadata.json` | Validation script runs; lineage reconciliation written; metadata finalised. | **final deliverable** |

**The reconciliation identity — this must always hold:**

```
n_raw_captured
  = n_extracted_to_interim
  = n_candidate_pool + Σ(n_excluded_by_reason.values())
  = n_labeled
  = n_usable_final
  = train + dev + test
```

If any row cannot be accounted for, it is a bug — not a rounding difference. `n_usable_final`
is the number that fills the paper's `<number>` placeholder.

**Which layer answers which question**

| Question | Answered by |
|---|---|
| "What exactly did the platform return?" | `data/raw/` |
| "What did we collect before making any judgment calls?" | `data/interim/` |
| "What was removed, and why?" | The exclusion ledger — reason codes `X_DUP_EXACT`, `X_DUP_NEAR`, `X_SPAM`, `X_LANG`, `X_EMPTY`, `X_OFFICIAL`, `X_PII` |
| "What is the labeled dataset a consumer should load?" | `data/processed/dataset_v1.csv` |
| "Which rows go in which split?" | `data/processed/splits/*.csv` |
| "Which government agency is this from?" | `agency_id` → `data/provenance/government_agencies.csv` |
| "Which post was it on?" | `post_id` → `data/processed/posts_v1.csv` |

---

## The government agency registry

`data/provenance/government_agencies.csv` is the canonical list of the Philippine
government entities in the study — one row per **(agency, platform)** pair.

| Column | Meaning |
|---|---|
| `agency_id` | Canonical ID, e.g. `dost_pagasa`. The only agency identifier used in the dataset. |
| `agency_name` / `agency_abbr` | Official full name and abbreviation, e.g. *Philippine Atmospheric, Geophysical and Astronomical Services Administration* / `DOST-PAGASA`. |
| `agency_type` | `national_government_agency`, `government_owned_and_controlled_corporation`, `government_corporation`, or `local_government_unit`. LGUs are out of scope. |
| `parent_department` / `parent_department_abbr` | Supervising department, e.g. *Department of Science and Technology* / `DOST`. |
| `official_website` | The agency's own site. Used to cross-check that the account is genuinely official. |
| `official_account_url` / `official_account_id` / `official_account_name` | The official account itself. The platform-side ID is what the collector matches against. |
| `platform` / `source_page` | Platform and the short slug used in `comment_id`. |
| `official_verified` / `verification_basis` | Whether the account is official, and how that was established (e.g. `linked_from_official_website`). |
| `comments_enabled` | Whether comments were publicly visible at collection time. |
| `domains` | Policy domains, e.g. `weather;disaster_preparedness`. |
| `eligibility_s1` … `eligibility_s6` | One column per source criterion in the contract. **All six must be `true`** to collect from. |
| `n_posts_planned` / `collection_method` | Collection plan for this account. |

One row per **(agency, platform)** pair — an agency with both a Facebook page and a YouTube
channel has two rows sharing one `agency_id`.

`agency_id` is **stable** across dataset versions, and `agency` / `agency_abbr` in the
dataset are denormalized copies that must match the registry exactly (check V-16).

---

## Dataset conventions

| Convention | Value |
|---|---|
| Primary dataset | `data/processed/dataset_v1.csv` — **Facebook only**, matching the study's framing |
| Extended dataset | `data/processed/dataset_v1_ext.csv` — all platforms; `dataset_v1` is exactly its `platform == "facebook"` subset |
| Modeling text field | `comment_text_norm` (comment only, no post context) |
| Label encoding | `1` = actionable, `0` = other — **use `pos_label=1`** |
| Government source | `agency_id` → `data/provenance/government_agencies.csv` — the canonical registry of Philippine government agencies and their official accounts |
| Split strategy | 70/15/15, stratified by label, grouped by `post_id`, seed `42` |
| Duplicate handling | Exact (`dedup_key`) and near (Jaccard ≥ 0.90) — **before** the split |
| Target size | ≥ 1,000 usable comments combined; ≥ 600 in the Facebook-only primary set |
| Reliability target | Cohen's κ ≥ 0.60 on the 20% blinded re-label subset (intra-annotator) |
| Missing values | Empty string (never `NA` / `null` / `None`) |
| `comment_id` | `<platform>_<source_page>_<seq4>`, e.g. `fb_dost_pagasa_0001` — never reused or renumbered |

---

## Status

| Stage | State | Output |
|---|---|---|
| Dataset contract v1.0 | 🔶 Draft — awaiting sign-off | `DATA_CONTRACT.md` |
| Annotation guidelines v1.0 | 🔶 Draft — awaiting team agreement | `docs/ANNOTATION_GUIDELINES.md` |
| Source list & collection protocol | ⬜ Blocked on instructor approval | `data/provenance/government_agencies.csv` |
| Collection pilot | ⬜ | raw snapshot + yield estimate |
| Full collection | ⬜ | raw snapshots, `collection_log.csv` |
| Cleaning, dedup, PII scrub | ⬜ | candidate pool + exclusion ledger |
| Reliability measurement | ⬜ | 20% blinded re-label, κ |
| Full annotation + resolution | ⬜ | labeled dataset |
| Splits + metadata + validation | ⬜ | splits, metadata, `validation_report.txt` |

🔶 in progress · ⬜ not started · ✅ complete

---

## Milestones

| ID | Milestone | Output | Depends on |
|---|---|---|---|
| M1 | Decisions D-1…D-6 settled | signed section in the contract | instructor + team |
| M2 | **G1 — schema freeze** | contract v1.0 | M1 |
| M3 | Source list frozen, collection protocol documented | `government_agencies.csv`, `COLLECTION_PROTOCOL.md` | M2 + approval |
| M4 | Collection pilot (2 pages × 2 posts) | raw snapshot + yield estimate | M3 |
| M5 | Full collection | raw snapshots, `collection_log.csv` | M4 |
| M6 | Cleaning, dedup, PII scrub | candidate pool + exclusion ledger | M5 |
| M7 | **G2 — data freeze** | pool size and exclusion counts known | M6 |
| M8 | Gold set (120 rows) labeled, κ computed against it | gold set, κ | M7 + guidelines v1.0 |
| M9 | Auto-annotator gate test (optional) | gate metrics | M8 |
| M10 | Full annotation + adjudication | labeled dataset | M8 / M9 |
| M11 | **G3 — label freeze** | splits, metadata | M10 |
| M12 | Validation passes, DATA_CARD written | `validation_report.txt`, `DATA_CARD.md` | M11 |
| M13 | Usable-comment count finalized for the write-up | number + breakdown table | M12 |

**Annotation is the long pole** — it needs four to five weeks of team time. Start it as soon
as the gold set exists; do not wait for collection to be "complete."

---

## Rules for working in this repo

- **Do not hand-edit `data/processed/*.csv`.** Regenerate from `data/raw/` via `src/clean/`.
- **Never commit** anything from `data/raw/` or `data/interim/`.
- **Never silently change a label, a split, or a `comment_id`.** New version, new file,
  changelog entry (`DATA_CONTRACT.md` §17).
- **Schema changes are a contract change.** Propose them in `DATA_CONTRACT.md` §18 first.
- **Bump `guideline_version`** whenever the annotation rules change, and re-annotate
  affected rows. Labels from different guideline versions are never mixed in one release.

---

## Source documents

| Document | What it governs here |
|---|---|
| `docs/NLP-PLAN.pdf` | Task assignment, proposed research, collection/annotation objectives |
| `docs/NLP-Final-Paper.pdf` | Label definitions, scope and limits, inclusion criteria |
| `DATA_CONTRACT.md` | Schema, dedup/spam/PII rules, splits, validation |
| `docs/ANNOTATION_GUIDELINES.md` | The labeling rules and example bank |
| `docs/STAGES.md` | The step-by-step path through this scope |

---

## License

Pending instructor review.
