# STAGES.md — Your path through the data stage

**Scope:** data collection, scraping, and annotation only.
**You are:** Member 4 (MALASAN) — the producer of the dataset.
**The finish line:** `data/processed/dataset_v1.csv` + `data/processed/splits/` handed over for modeling.

> **Correction to a common assumption:** you do **not** start at scraping. You start at
> **Stage 0 — choosing the pages**. The scraper needs a list of accounts and an `agency_id`
> to stamp on every row, and that list is frozen *before* collection begins. Everything after
> that is mechanical.

---

## The path at a glance

```
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 0  SELECT SOURCES          decide which accounts to read │
│            → government_agencies.csv                              │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 1  COLLECT (RAW)         read the public HTML/DOM        │
│            → data/raw/                                           │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 2  CLEAN                dedup → spam → PII scrub         │
│            → data/interim/ → candidate pool                     │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 3  ANNOTATE             guidelines → 100% → re-label │
│            → labeled dataset                                    │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 4  SPLIT                70/15/15, grouped by post_id     │
│            → data/processed/splits/                             │
└──────────────────────────┬──────────────────────────────────────┘
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  STAGE 5  VALIDATE & DELIVER   16 checks, then hand off        │
│            → dataset_v1.metadata.json                           │
└─────────────────────────────────────────────────────────────────┘
```

**Stages 0–2 are yours alone.** Stage 3 needs the whole team. Stages 4–5 are yours again.

---

## Stage 0 — Select the sources

**Goal:** a frozen, defensible list of official Philippine government accounts to read.

- [ ] Pick the agencies. 4–6 across at least 2 policy domains (e.g. `DOST-PAGASA`, `DSWD`,
      `DPWH`, `DepEd`, `DOH`). The paper says "selected national government agencies" —
      pick a spread, not 6 agencies from one domain.
- [ ] For each, find the **official** account. Verify it, don't assume: check the agency's own
      website links to it, or that it carries official/verified status.
- [ ] Confirm **comments are enabled** and publicly visible without logging in.
- [ ] Record the **platform account ID** (numeric page ID / channel ID) from the page source —
      the scraper uses it to match a captured page back to your registry row.
- [ ] Note the **policy domains** the agency covers (e.g. `weather;disaster_preparedness`).
- [ ] Fill in `data/provenance/government_agencies.csv` — every row needs all six
      `eligibility_s1`…`s6` set to `true`.
- [ ] Fill in `n_posts_planned` (8–12 per account) and `collection_method`.
- [ ] Write up `docs/COLLECTION_PROTOCOL.md`.

**Done when:** `government_agencies.csv` has ≥ 4 rows, every `eligibility_s*` is `true`, and
`COLLECTION_PROTOCOL.md` exists.

**Blocks:** everything. You cannot scrape without this file.

---

## Stage 1 — Collect (raw)

**Goal:** raw payloads on disk, exactly as the platform returned them. No filtering.

- [ ] Build the Facebook scraper in `src/collect/facebook.py` — headless browser (Playwright),
      open the public permalink, scroll the comment thread, read the rendered DOM.
- [ ] Build the YouTube parser in `src/collect/youtube.py` — `requests` + `ytInitialData`
      continuation tokens.
- [ ] Build the Reddit fetcher in `src/collect/reddit.py` — public `.json` endpoints.
- [ ] Write each raw payload **once** to `data/raw/<platform>/<page>/<run_id>.json`. Never edit
      it afterwards.
- [ ] Log every run to `data/provenance/collection_log.csv` — tool, version, `user_agent`,
      `delay_seconds`, counts, and anything that went wrong.
- [ ] Do the **pilot first**: 2 pages × 2 posts. Estimate the comment yield per post before
      committing to the full run.
- [ ] Scale to the full collection: 8–12 posts per account.

**Done when:** `data/raw/` holds a snapshot per run, `collection_log.csv` has a row per run,
and the pilot's yield estimate says you can reach **≥ 1,000 usable comments combined**, of which
**≥ 600 must be Facebook** (that Facebook-only set is the paper's primary dataset).

**Watch out:** Facebook renders comments client-side. A plain `requests` fetch usually returns
only the post shell. Use a fixed delay between requests and a realistic `User-Agent`, or you
get IP-blocked and lose collection time.

---

## Stage 2 — Clean

**Goal:** one candidate row per genuinely usable comment, with every removal accounted for.

**2a — Extract** (no filtering yet)
- [ ] Flatten each raw snapshot into `data/interim/comments_captured.csv` and
      `posts_captured.csv` — one row per comment, one per post, text still verbatim.

**2b — Filter**
- [ ] Apply the exclusion rules in `DATA_CONTRACT.md` §4.2 — every removal gets a reason code
      (`X_DUP_EXACT`, `X_DUP_NEAR`, `X_SPAM`, `X_LANG`, `X_EMPTY`, `X_OFFICIAL`, `X_PII`).
- [ ] **No silent drops.** The exclusion counts belong in the write-up.
- [ ] Never filter on sentiment, profanity, politics, or length beyond empty-text removal.

**2c — Normalize**
- [ ] Apply the §6.2 rules in order → `comment_text_norm`, `context_text_norm`, `dedup_key`.
- [ ] Keep original casing, punctuation, and emoji. Do not lowercase the shipped file.

**2d — Deduplicate**
- [ ] Exact duplicates by `dedup_key` — keep the earliest captured.
- [ ] Near-duplicates by token Jaccard ≥ 0.90 — keep the longer, cap at 2 per account per post.
- [ ] Do this **before** the split, or the model gets tested on text it has seen.

**2e — Anonymize**
- [ ] Scrub names, `@mentions`, phone, email, addresses, ID-like digit runs → `<USER>`,
      `<PHONE>`, `<EMAIL>`, `<NUM>`, `<URL>`.
- [ ] Set `pii_redacted` on every row the scrub touched.
- [ ] Never store commenter handles or profile URLs in the processed dataset at all.

**Done when:** the candidate pool exists, the exclusion ledger totals correctly, and
`n_raw_captured − Σ(exclusions) = n_candidate_pool`.

**Gate G2 — data freeze.** The pool size and exclusion counts are now known.

---

## Stage 3 — Annotate

**Goal:** every comment labeled `1` (actionable) or `0` (other), with measured agreement.

**Labeling is automated** by `src/annotate/auto_annotator.py`, with human verification of
≥ 100 rows and a blinded re-label pass for the reliability number. You are not
hand-labeling a thousand comments — you are adjudicating the ambiguous ones and
verifying a sample.

**3a — Guidelines**
- [ ] Read `docs/ANNOTATION_GUIDELINES.md` §2 (the core rule) and §5 (the example bank) end
      to end before labeling anything.
- [ ] Label a **30-row pilot batch**, writing the reason for each label in the note field.
- [ ] Compare your reasoning against the example bank. Where it contradicts the bank, the
      guideline is wrong → amend it and bump `guideline_version`.

**3b — Production pass**
- [ ] Run `python src/annotate/auto_annotator.py score` on the pool → confident rows are
      labeled automatically, the rest are exported for adjudication.
- [ ] Work the review batches (every low-confidence row + a 10% audit sample of the rest).
      Each batch carries the comment, the post context and the parent's text.
- [ ] Merge the decisions back with `auto_annotator.py apply`.
- [ ] Set `label`, `label_str`, `language`, and `verification` on every row.

**3c — Washout**
- [ ] Leave the data alone for **≥ 7 days**. Don't look at your labels.
- [ ] This is what makes the next pass a measurement instead of a memory test.

**3d — Blinded re-label pass**
- [ ] Re-label a random **20% subset (≥ 200 rows)**, stratified by class and source page.
- [ ] The labeling tool must **hide `label`** for this pass. If you can see your earlier answer,
      the pass is worthless.
- [ ] Store the second reading in `label_2`.

**3e — Reliability**
- [ ] Compute Cohen's κ between `label` and `label_2`. **Gate: κ ≥ 0.60.**
- [ ] If κ < 0.60 → read every disagreement, resolve it against the guidelines (not by
      keeping whichever you wrote first), amend the guidelines if they were unclear, bump the
      version, re-annotate the affected rows, and re-measure.

**3f — Human verification (required)**
- [ ] Verify **≥ 100 random rows** that the engine labeled, **without seeing its label
      first**.
- [ ] Record the agreement rate and Cohen's κ between your reading and the engine's.
- [ ] Set `verification = human_verified` on those rows.
- [ ] Report both numbers in the write-up.

**3g — Auto-annotator audit**
- [ ] Evaluate a candidate assistant against a **120-row self-labeled gold set**.
- [ ] Gate: **macro-F1 ≥ 0.80 AND κ ≥ 0.60** against your gold set. Below that, don't
      use it — record the attempt as a negative result.
- [ ] If it passes: pre-label only, **every** draft human-confirmed by you. Assistant labels are
      **excluded** from the reliability computation (no circularity).
- [ ] Label your own pool first, then use the assistant only for rows you haven't reached.
- [ ] If you use a hosted assistant, send only `comment_text_norm` after the scrub, never
      `post_text`.

**3g — Finalize**
- [ ] Resolve every pass-1 vs pass-2 disagreement → `label`, `adjudicated_by`,
      `adjudication_note`.
- [ ] Add each resolved case to the example bank in the guidelines.
- [ ] Compute and report the final κ.

**Done when:** every row has a label, κ ≥ 0.60 on the re-labeled subset, and
`guideline_version` is set on every row.

> **How to describe this in the write-up:** *intra-annotator reliability*, measured by a blinded
> re-annotation pass after a 7-day washout. **Not** inter-annotator agreement — there is only
> one annotator, and calling it that is a misreport.

---

## Stage 4 — Split

**Goal:** a fixed, leakage-free partition that both models share.

- [ ] 70 / 15 / 15, **stratified by label**.
- [ ] **Grouped by `post_id`** — the same post's comments never straddle two splits, or the
      model is scored on its own vocabulary.
- [ ] Seed `42`. Fixed and recorded in the metadata.
- [ ] Write `data/processed/splits/{train,dev,test}.csv`.
- [ ] Copy the assignment into the `split` column of `dataset_v1.csv` — the **files** are
      authoritative, the column is a mirror.
- [ ] Check the class prior in test is within ±10 points of train.

**Done when:** every `comment_id` appears in exactly one split file, and counts match.

---

## Stage 5 — Validate & deliver

**Goal:** a dataset that can be accepted or rejected with one command.

- [ ] Write `tools/validate_dataset.py` — the 16 checks V-01…V-16 from the contract.
- [ ] Run it. **0 errors**, or fix the underlying problem (don't weaken the check).
- [ ] Fill in `data/processed/dataset_v1.metadata.json` — including the `lineage` block, which
      must satisfy the reconciliation identity.
- [ ] Write `docs/DATA_CARD.md`.
- [ ] Confirm the row-count reconciliation holds:
      `n_raw_captured = n_candidate_pool + Σ exclusions = n_labeled = n_usable_final = train+dev+test`
- [ ] Note the final usable count → this is the number that fills the paper's `<number>`
      placeholder in the Scope section.

**Done when:** `validation_report.txt` shows 0 errors, and the deliverable is:

| File | What it is |
|---|---|
| `data/processed/dataset_v1.csv` | The labeled dataset, 35 columns. **Facebook only** — matches the paper title and abstract. |
| `data/processed/dataset_v1_ext.csv` | The same schema across all platforms. Optional extension. |
| `data/processed/splits/{train,dev,test}.csv` | **Authoritative** split assignment. Join on `comment_id`. |
| `data/processed/posts_v1.csv` | Post context master. |
| `data/processed/dataset_v1.metadata.json` | Counts, class distribution, per-agency counts, provenance, κ, lineage. |
| `data/provenance/government_agencies.csv` | Which government agency every row came from. |
| `data/final/` | **The release package.** Assembled by `tools/build_release.py` — one folder, one zip, one manifest. |

The 35 columns, in order: `comment_id`, `platform`, `source_page`, `source_page_name`,
`agency_id`, `agency`, `agency_abbr`, `post_id`, `post_url`, `post_date`, `post_text`,
`post_media_type`, `post_topic`, `is_reply`, `parent_comment_id`, `parent_comment_text`,
`comment_text`, `comment_text_norm`, `context_text_norm`, `dedup_key`, `n_tokens`, `language`,
`label`, `label_str`, `annotator_id`, `label_2`, `agreement`, `adjudicated_by`,
`adjudication_note`, `guideline_version`, `source_snapshot`, `collected_at`, `pii_redacted`,
`split`, `notes`.

**Gate G3 — label freeze.**

---

## The hand-off to modeling

**What lands on the modeling side's desk:**

```
data/processed/dataset_v1.csv          ← the labeled dataset
data/processed/splits/train.csv        ← authoritative
data/processed/splits/dev.csv          ← authoritative
data/processed/splits/test.csv         ← authoritative  ← the held-out set, used ONCE
data/processed/posts_v1.csv            ← post context, if needed
data/processed/dataset_v1.metadata.json
data/provenance/government_agencies.csv
```

**What the modeling side does with it:** TF-IDF + Logistic Regression as the baseline, then
the same classifier plus the suggestion-related linguistic features (`please`, `dapat`, `sana`,
`paki-`), then both models compared on **the same** `test.csv`.

**Three rules that make the comparison valid** — worth saying out loud at hand-off:

1. **Both models score the same test set.** That is the entire basis of the comparison.
2. **The text field is `comment_text_norm` only.** If post context gets mixed into the feature
   space, you are testing a third, unreported model.
3. **`pos_label=1` on every metric call.** Flipped, every number inverts.

The load snippet is in `data/README.md`.

---

## Does your assigned task cover this scope?

Your task from `docs/NLP-PLAN.pdf`:

> *Identify official government pages, collect comments using an authorized method, clean the
> dataset (remove exact duplicates and spam), anonymize data, manually annotate comments.
> Though if there's an accurate auto annotator that can help, go.*

**Note:** the original wording said *"(everyone will help with this)"*. That clause is **dropped** —
the annotation is done by a single annotator, so the design and the reliability measurement both
change accordingly (§3a–§3g).

| Task item | Stage | Covered? |
|---|---|---|
| Identify official government pages | **0** | ✅ `government_agencies.csv` |
| Collect comments using an authorized method | **1** | ✅ `data/raw/` — public HTML/DOM, no credentials |
| Clean the dataset (remove exact duplicates and spam) | **2b, 2d** | ✅ `X_DUP_EXACT`, `X_DUP_NEAR`, `X_SPAM` |
| Anonymize data | **2e** | ✅ PII scrub, `X_PII` |
| Manually annotate comments | **3a–3g** | ✅ 100% pass + blinded 20% re-label + κ |
| Auto annotator, if accurate | **3f** | ✅ gated on macro-F1 ≥ 0.80 and κ ≥ 0.60 |

**Fully covered.** Six for six.

**Four things this scope adds that the task does not name** — all of them are required to
deliver a dataset the modeling stage can actually use:

| Addition | Why it is in scope anyway |
|---|---|
| **Split generation** (Stage 4) | The paper's objective 4 requires *"the same held-out test dataset"* for both models. Somebody has to produce it. |
| **Validation script** (Stage 5) | Turns "the dataset is fine" into a command anyone can run. Also the thing that lets the modeling side accept or reject your delivery. |
| **Post context capture** | You asked for it. It also makes replies annotatable — a large share of replies are uninterpretable without the parent post. |
| **Multi-platform extension** | Your task says "government pages"; the paper says Facebook. `dataset_v1.csv` is Facebook-only so the paper stays exact, and the other platforms live in `dataset_v1_ext.csv`. |

**Explicitly out of this scope:** sentiment labels, model training, feature engineering,
evaluation, and the paper's results and conclusion.

---

## Decision log — the open questions still blocking you

| # | Question | Why it blocks | When |
|---|---|---|---|
| D-1 | Which agencies exactly? | Nothing can be scraped until the source list exists | Stage 0 |
| D-2 | Facebook-only, or add YouTube/Reddit too? | Decides the scope of the collection run | Stage 0 |
| D-4 | Confirm solo annotation and the reliability method | The re-label pass needs 20% of the pool reserved and a 7-day gap built into the schedule | Before Stage 3d |
| D-5 | Which auto-annotator candidate, and does it run locally? | The gate needs a gold set first | Stage 3f |
| D-6 | Which labeling tool? | Must show post context and hide other annotators' labels | Before Stage 3a |
| D-7 | Final usable count for the paper's `<number>` | Fills the Scope placeholder | Stage 5 |

The full list is in `DATA_CONTRACT.md` §18.

---

## The critical path

If you only remember one thing:

> **Annotation is the long pole.** Stages 0–2 are a few weeks of your own work. Stage 3 needs
> four to five weeks of **your own** time, and it can't start until the gold set exists.
> So the moment Stage 2 produces a clean candidate pool, **start annotating** — do not wait for
> collection to be "finished," and do not wait for every decision to be settled.
>
> Second thing: **Stage 1 will not work on the first try.** Facebook's DOM selectors break, the
> comment list may not render, you may get blocked. Budget for two or three iterations on the
> Facebook scraper before touching anything else.

---

## Current status

- [x] Read the plan and the paper
- [x] Write `DATA_CONTRACT.md` — schema, rules, validation
- [x] Write `docs/ANNOTATION_GUIDELINES.md` — rules, decision tree, 50-example bank
- [x] Create the `data/` tree and every schema file
- [x] Create `tools/` placeholder and `src/` structure
- [x] Decide the collection method (public HTML/DOM, no credentials)
- [ ] **Stage 0** — pick the agencies, fill `government_agencies.csv`
- [ ] **Stage 1** — build the scrapers, pilot, full collection
- [ ] **Stage 2** — extract, filter, normalize, dedup, anonymize
- [ ] **Stage 3** — guidelines calibration, 100% labeling, washout, blinded re-label, κ
- [ ] **Stage 4** — split
- [ ] **Stage 5** — validate, metadata, data card, hand-off
- [ ] **Release** — `python tools/build_release.py --build --zip`
