# DATA_CONTRACT.md

**Dataset Contract — Detecting Actionable Suggestions in Filipino-English Code-Switched Government Social Media Comments**

| Field | Value |
|---|---|
| Contract version | `1.0-draft` |
| Status | **DRAFT — awaiting adviser + team sign-off** |
| Created | 2026-10-20 |
| Owner / Producer | Member 4 — **Edison Yin Malasan** (data collection, scraping, annotation) |
| Consumers | Member 5 — **Jim Hendrix Bag-eo** (model development) · Member 6 — **Henri Louis Agustin** (results, conclusion, final editing) |
| Applies to | `data/processed/dataset_v1.csv`, `data/processed/dataset_v1_ext.csv`, `data/processed/posts_v1.csv` |
| Governing documents | `docs/NLP-PLAN.pdf` (task assignment), `docs/NLP-Final-Paper.pdf` (scope, objectives, RQ), `docs/ANNOTATION_GUIDELINES.md` (label rules) |
| Related outputs | `data/processed/dataset_v1.metadata.json`, `docs/DATA_CARD.md` |

---

## 0. How to read and use this document

This contract is the **agreement between the data producer (Member 4) and the data consumer (Member 5)**. It states exactly what dataset will be delivered, in what shape, with what guarantees, so that Member 5 can write and run the model without guessing.

**Three rules govern this document:**

1. **Anything Member 5 depends on is normative.** Schema, column names, label encoding, split files, and the modeling text field are *binding*, not suggestions.
2. **Anything not written here is not guaranteed.** If Member 5 needs a field that is not in §5, it does not exist — request it via §17 (change control) *before* coding, not after.
3. **Producer-side choices are free to change; the interface is not.** Member 4 may change collection pages, tool versions, or cleaning internals without breaking the contract, provided the interface in §5–§6 holds and the contract is not silently violated.

**Version discipline:** the contract is versioned and frozen at three gates. See §16.

| Gate | When | What is frozen |
|---|---|---|
| **G1 — Schema freeze** | Before any collection begins | §4–§6, §13. Changes after this require adviser approval. |
| **G2 — Data freeze** | After cleaning + dedup + anonymization, before annotation | The candidate pool. §5 holds; row count is now known. |
| **G3 — Label freeze** | After adjudication, before splits are released | §10–§12, labels, splits, `dataset_v1.metadata.json`. |

---

## 1. Purpose and scope

### 1.1 Purpose

To produce a **reproducible, documented, anonymized, human-labeled dataset** of public government social media comments that (a) supports the binary task defined in the paper and (b) is stable enough that the two models compared in the paper (TF-IDF + Logistic Regression baseline vs. the same classifier augmented with suggestion-related linguistic features) are evaluated on an identical, leakage-free test set.

### 1.2 In scope (this contract covers)

- Source selection: official Philippine national government agency accounts on public social media platforms.
- Collection: automated retrieval by reading the **publicly visible HTML/DOM** of each post page, with a manual-capture fallback. No API keys or credentials are required.
- Cleaning: exact and near-duplicate removal, spam/low-value filtering, bot-signature removal.
- Anonymization: removal of personal identifiers and any re-identification pathway.
- Annotation: binary labeling into `actionable` / `other` under `docs/ANNOTATION_GUIDELINES.md`, with double annotation, agreement measurement, and adjudication.
- Delivery: dataset files, split files, metadata, provenance records, and a validation script.

### 1.3 Out of scope (explicitly not delivered)

- Sentiment labels. The paper's task is **not** sentiment analysis (§2.1). Adding a sentiment column is out of scope and would invite an off-paper comparison.
- Any assessment of factual accuracy of comments, feasibility of proposals, or government responsiveness (§1.3 of the paper's Scope).
- Real-world usefulness claims about the government agencies' handling of feedback.
- Re-linking comments to individuals, profiles, or account IDs. **Never**, in any artifact (§11).

### 1.4 Deliverables this contract produces

| ID | Deliverable | Due (proposed) | Owner |
|---|---|---|---|
| D-01 | `docs/ANNOTATION_GUIDELINES.md` v1.0 | Before gold-set labeling | M4 |
| D-02 | `data/provenance/government_agencies.csv` | Before collection | M4 |
| D-03 | Raw snapshots under `data/raw/` (immutable) | During collection | M4 |
| D-04 | `data/interim/comments_captured.csv` | End of collection | M4 |
| D-05 | `data/processed/dataset_v1.csv` (cleaned, anonymized, unlabeled → then labeled) | G2 / G3 | M4 |
| D-06 | `data/processed/dataset_v1.metadata.json` | G3 | M4 |
| D-07 | `data/processed/splits/{train,dev,test}.csv` | G3 | M4 |
| D-08 | `tools/validate_dataset.py` + passing report | Before hand-off | M4 |
| D-09 | `docs/DATA_CARD.md` | Before hand-off | M4 |
| D-10 | Confirmed usable-comment count for the paper's `<number>` placeholder | G3 | M4 → M6 |

---

## 2. Task definition carried over from the paper

### 2.1 Label taxonomy

Exactly two labels. The wording below is taken from `docs/NLP-Final-Paper.pdf` (Scope) and is normative.

> **Actionable suggestion/request** — a comment that *proposes an identifiable action* or *asks for a specific action or response*.
>
> **Other comment** — a comment that does not meet this definition.

Binding clarifications from the paper:

- **Complaints without a proposed action → `other`.**
- **General wishes without an identifiable action → `other`.**
- The task is **action/need detection, not sentiment**. A comment may be negative in sentiment and still be `other` (e.g., *"Ang pangit ng kalsada namin"*).
- Every comment receives **exactly one** label.

### 2.2 The language-neutrality rule (critical, do not skip)

The label is defined by **whether an action is identified**, never by the presence of a surface marker.

> ❌ WRONG: "A comment containing *please*, *dapat*, *sana*, or *paki-* is actionable."
> ✅ RIGHT: "A comment identifying a concrete action the government should take is actionable. The presence of politeness markers is *evidence*, not the definition."

**Why this is binding:** the paper's research question asks whether *adding* suggestion-related linguistic features (the markers above) improves detection over a TF-IDF baseline. If the annotation rule were marker-based, the answer would be trivially yes and the study would measure nothing. §2.2 exists to protect the validity of the paper's central comparison. The full reasoning is repeated in `docs/ANNOTATION_GUIDELINES.md` §2.

### 2.3 Research question this dataset must support

> Does incorporating suggestion-related linguistic features improve the detection of actionable suggestions and requests in Filipino-English code-switched government social media comments compared with a TF-IDF and Logistic Regression baseline?

Consequently: **the primary modeling text field is the comment alone.** See §6.4.

---

## 3. Data sources and collection protocol

### 3.1 Source selection criteria (all must hold)

A source account is eligible if:

| # | Criterion | Rationale |
|---|---|---|
| S1 | It is the **official** account of a Philippine **national** government agency (or a clearly identified national-government program/body). | Matches the paper's scope ("selected Philippine national government agencies"). |
| S2 | It is a **verified** / official account, not a fan page, advocacy group, or personal account of an official. | Prevents partisan or unofficial commentary from being labeled as agency content. |
| S3 | Comments are **enabled** and publicly visible without login or request. | Collection feasibility. |
| S4 | It has **enough publicly visible comment volume** to yield a meaningful share of comments. | Practical yield. |
| S5 | It publishes in a domain where the agency plausibly receives **citizen requests** (services, infrastructure, weather/warnings, health, education, disaster response, announcements requiring compliance). | The task needs actionable content to exist; a page that only posts memes would not. |
| S6 | It is **not** a page whose content is predominantly non-text (e.g., video-only reposts of unrelated viral content). | Annotation feasibility. |

Excluded source types: political party pages, personal accounts of officials, news media organizations, private businesses, NGO/advocacy accounts, and "supporter" fan pages.

**Source list is frozen at G1** and recorded in `data/provenance/government_agencies.csv`. Any addition after G1 must be justified in the paper (e.g., "an additional agency was added to satisfy S5") and recorded in the changelog (§17).

### 3.1b The government agency registry (`government_agencies.csv`)

Every source in this study is an account of a **Philippine national government agency**. That
agency is recorded once, in a canonical registry, and referenced by `agency_id` everywhere
else. This keeps the dataset self-describing: any row can be traced to a real, named
government body, and the same agency is spelled identically everywhere.

**File:** `data/provenance/government_agencies.csv` — one row per agency.

| Column | Type | Description |
|---|---|---|
| `agency_id` | slug | Canonical ID, e.g. `dost_pagasa`. Primary key. |
| `agency_name` | string | Official full name, e.g. *Philippine Atmospheric, Geophysical and Astronomical Services Administration*. |
| `agency_abbr` | string | Official abbreviation, e.g. `DOST-PAGASA`. |
| `agency_type` | enum | `national_government_agency` \| `government_owned_and_controlled_corporation` \| `government_corporation` \| `local_government_unit`. **Only `national_government_agency` and government corporations operating nationwide are in scope** (§3.1 S1) — LGUs are out of scope. |
| `parent_department` | string | Supervising department, e.g. *Department of Science and Technology*. Empty for standalone constitutional offices. |
| `parent_department_abbr` | string | e.g. `DOST`. |
| `official_website` | URL | The agency's own website. Used to cross-check that the social account is genuinely official. |
| `official_account_url` | URL | The official social account used as the source. |
| `official_account_id` | string | Platform-side account ID (numeric page ID, channel ID) as it appears in the page source. Used to match a captured page to the registry row. |
| `official_account_name` | string | Display name of the account as it appears on the platform. |
| `platform` | enum | `facebook` \| `youtube` \| `reddit` \| `x`. One row per **(agency, platform)** pair. |
| `source_page` | slug | Short slug used in `comment_id` and `source_page`, e.g. `dost_pagasa`. |
| `official_verified` | bool | `true` — the account carries official/verified status or is linked from the agency's own website. |
| `verification_basis` | string | How officiality was established, e.g. `linked_from_official_website`, `blue_check`, `linked_from_agency_website`. |
| `comments_enabled` | bool | Whether comments were publicly visible at collection time. |
| `domains` | string | `;`-separated policy domains, e.g. `weather;disaster_preparedness`. Used for stratification and reporting. |
| `eligibility_s1` … `eligibility_s6` | bool | One column per source criterion in §3.1. **All six must be `true`** for the row to be collected from. |
| `n_posts_planned` | int | How many posts of this account are planned for collection. |
| `collection_method` | enum | `dom_headless` \| `html_parse` \| `json_endpoint` \| `manual_capture`. |
| `notes` | string | Free text. |

**Rules**

1. `agency_id` is **stable** across dataset versions. If an agency's official account changes, the row is updated and the change is noted in the changelog — the `agency_id` does not change.
2. **One row per (agency, platform).** An agency with a Facebook page and a YouTube channel has two rows sharing one `agency_id`.
3. `agency_id` is the **only** agency identifier that appears in `dataset_v1.csv`. `agency` and `agency_abbr` are denormalized convenience copies and **must** match the registry exactly (validation check V-16).
4. The registry is **frozen at G1**. Adding an agency after G1 requires the §17 change log.
5. The registry is a **reference table about government entities** — it contains no comment data and no personal data.
7. This file **replaces** a separate `government_agencies.csv`. There is exactly one list of sources, and the registry is it. Two overlapping source lists would drift apart and silently contradict each other.



### 3.2 Platforms and collection routes

Comments are collected by **reading the publicly visible HTML/DOM** of each post page. **No API keys, access tokens, OAuth apps, or account credentials are required, and none are stored in this repository.** Every route below is keyless.

| Platform | Route | What is read | Viability | Role |
|---|---|---|---|---|
| **Facebook** | Headless browser (Playwright) that opens the public post permalink, scrolls the comment thread, and reads the rendered DOM | `div[aria-label]` / `data-testid` comment nodes, author handle, timestamp, and the parent post caption | **High** | **Primary.** Matches the paper title/abstract exactly. |
| Facebook (fast path) | `requests` fetch of the public permalink, parsing the HTML/embedded JSON already present in the page source | Same fields where the server returns them without client-side rendering | Medium | Faster per post; falls back to the headless browser when the comment list is not in the source. |
| **YouTube** | `requests` fetch of the watch page, parsing `ytInitialData` / `ytInitialData` continuation tokens from the HTML | Comment text, author, timestamp, reply threads | **High** | Secondary. Agency channels (DSWD, PAGASA, DepEd, DOH) have active videos with heavy comment volume. |
| **Reddit** | Public keyless JSON endpoints (`/comments/<id>.json`, `/r/<sub>/comments.json`) | Comment body, author, score, created time | Medium-Low | Optional. Government-specific threads are sparse; yield unpredictable. |
| **X / Twitter** | Public page HTML / embedded JSON | Replies under agency posts | Low | Optional. Mostly client-rendered; lowest yield of the four. |
| TikTok / others | — | — | **Not viable** | Out of scope. Do not attempt. |

**Practical notes per platform**

- **Facebook**: the comment list is client-rendered, so a plain `requests` fetch often returns the post shell without comments. The headless browser (scroll-to-bottom, wait for the thread to grow) is the reliable route; the raw HTML route is only a shortcut when the comments happen to be in the page source.
- **YouTube**: the watch page embeds the first page of comments in `ytInitialData`; further pages come from continuation tokens in the same payload. No key needed.
- **Reddit**: the `.json` endpoints are public and keyless. Send a descriptive `User-Agent` header or the requests get throttled.
- **X**: replies are the least accessible of the four and are frequently behind a login wall. Treat as optional.

**Rate behavior (operational, not policy).** Send requests slowly with a fixed delay between them and rotate a realistic `User-Agent`. Going too fast gets the client IP temporarily blocked, which costs data collection time — the delay is a throughput decision, not a formality. When a request returns a block or a consent interstitial, log it in `collection_log.csv` and stop that source for the run rather than retrying in a loop.

### 3.3 Collection parameters (recorded per source, per run)

Every collection run is logged to `data/provenance/collection_log.csv`:

| Column | Description |
|---|---|
| `run_id` | e.g. `fb_dost_pagasa_2026-10-22T09-30` |
| `platform` | `facebook` / `youtube` / `reddit` / `x` |
| `source_page` | slug of the source account |
| `collection_method` | `dom_headless` / `html_parse` / `json_endpoint` / `manual_capture` |
| `tool` / `version` | e.g. `playwright 1.47` / `beautifulsoup4 4.12` / `requests 2.32` |
| `user_agent` | the `User-Agent` string used for the run |
| `delay_seconds` | fixed delay between requests for this run |
| `post_ids_collected` | count of posts touched |
| `comments_collected` | count of raw comments retrieved |
| `collected_at` | ISO 8601 timestamp (UTC) |
| `raw_snapshot_id` | link to the immutable payload file under `data/raw/` |
| `notes` | scroll depth, pages retrieved, errors, blocks encountered |

**Snapshot immutability:** raw payloads are written once to `data/raw/<platform>/<source_page>/` and are **never edited**. Cleaning is reproducible from raw via `src/clean/`. `data/raw/` is gitignored for size; processed artifacts are committed.

### 3.4 Collection window and target volume

| Item | Value |
|---|---|
| Collection window | To be fixed at G1. Proposed: **2026-10-22 → 2026-11-15** |
| Post selection | For each source: a **contiguous, documented sample of the most recent N public posts** (proposed N = 8–12), starting from the collection date and walking backwards. "Most recent" is fixed and logged — **no cherry-picking posts by comment richness**. |
| Target: usable comments | **≥ 1,000** after cleaning, dedup, and exclusion (this is the number that fills the paper's `<number>` placeholder) |
| Target: usable comments, primary (Facebook-only) dataset | **≥ 600** (minimum viable for the paper's headline comparison) |
| Minimum class representation | **≥ 150 actionable** and **≥ 150 other** in the primary dataset. If the natural yield of `actionable` falls below this, switch to **deliberate stratified collection** (sample additional posts known to solicit citizen input, e.g. consultation posts, "how can we improve" posts, service-announcement posts with open questions) and document the sampling design and the natural class prior. |
| Language mix | Comments must be Filipino, English, or mixed. Comments in other languages are **excluded at collection time** (see §4.2), not labeled `other`. |

---

## 4. Inclusion and exclusion criteria

### 4.1 Inclusion (a comment enters the candidate pool if all hold)

- I1 — It is a **public comment** on a post from an eligible source account (§3.1).
- I2 — It is authored by a **non-official account** (not the agency's own page, not a verified partner/partner-official account posting on its own behalf).
- I3 — Its language is **Filipino, English, or a mix of both** (§10.4).
- I4 — It is **not** exact-duplicate and **not** near-duplicate of a retained comment (§7).
- I5 — It is **not** spam / promotional / automated (§8).
- I6 — It contains **at least one word token** after normalization (§6.2).
- I7 — It passes the **anonymization** checks in §11 (no unredacted PII survives into the delivered dataset).

### 4.2 Exclusion and removal (with reason codes)

Every excluded row is **counted and logged with a reason code** — the exclusion ledger is reported in the paper's Methodology and in `dataset_v1.metadata.json`. Silent drops are not acceptable.

| Code | Condition | Stage |
|---|---|---|
| `X_SRC` | Comment not from an eligible source | collection |
| `X_OFFICIAL` | Author is the agency / official / partner account | cleaning |
| `X_LANG` | Language is not fil / eng / mixed | cleaning |
| `X_EMPTY` | No word tokens after normalization (emoji-only, punctuation-only, single link) | cleaning |
| `X_DUP_EXACT` | Exact duplicate of an earlier retained comment (§7.1) | cleaning |
| `X_DUP_NEAR` | Near-duplicate of a retained comment (§7.2) | cleaning |
| `X_SPAM` | Matches a spam / promotion / bot rule (§8) | cleaning |
| `X_PII` | Contains personal data that cannot be safely redacted (§11.2) | cleaning |
| `X_DELETED` | Comment deleted or hidden by the platform after capture | pre-delivery |
| `X_UNREADABLE` | Payload corrupted / text could not be reconstructed | pre-delivery |

### 4.3 What is **not** an exclusion reason

- Negative sentiment. A harsh complaint is data, not noise.
- Short comments. `"Please fix."` is a valid actionable comment.
- Political content that is not spam — the task is to detect *proposals and requests*, which often appear in political complaints.
- Duplicate content **across different posts** is a near-duplicate concern (§7.2), not automatically a removal; the decision is logged.

---

## 5. Dataset schema (normative)

### 5.1 File inventory

| File | Rows | Grain | Description |
|---|---|---|---|
| `data/processed/dataset_v1.csv` | one per usable comment | comment | **Primary dataset. Facebook only** (paper-faithful). |
| `data/processed/dataset_v1_ext.csv` | one per usable comment | comment | **Extended dataset.** All platforms. Same schema. `dataset_v1` is exactly the subset where `platform == "facebook"`. |
| `data/processed/posts_v1.csv` | one per source post | post | Post context master (§6.3). |
| `data/processed/splits/train.csv` | one per comment | comment | Split assignment + join keys. |
| `data/processed/splits/dev.csv` | " | " | " |
| `data/processed/splits/test.csv` | " | " | " |
| `data/processed/dataset_v1.metadata.json` | — | — | Counts, provenance, versions, agreement statistics. |
| `data/interim/comments_captured.csv` | one per captured comment | comment | Verbatim union of raw snapshots, pre-cleaning. |
| `data/interim/posts_captured.csv` | one per captured post | post | Verbatim post metadata. |
| `data/provenance/government_agencies.csv` | one per (agency, platform) | agency | **Canonical registry of the Philippine government entities and their official accounts** (§3.1b). |
| `data/provenance/government_agencies.csv` | one per source | account | The frozen source list (§3.1). |
| `data/provenance/collection_log.csv` | one per collection run | run | Collection audit trail (§3.3). |

### 5.2 `dataset_v1.csv` columns

CSV encoding `utf-8` (no BOM), `,` delimiter, `"` quoting, `\n` line endings, header row always present. Empty values are the **empty string**, never `NA`/`None`/`null`.

| # | Column | Type | Req. | Allowed values / format | Description |
|---|---|---|---|---|---|
| 1 | `comment_id` | string | yes | `^[a-z]+_[a-z0-9_]+_\d{4}$` | Globally unique, stable across versions. Pattern: `<platform>_<source_page_slug>_<seq>`, e.g. `fb_dost_pagasa_0001`. **Never reused, never renumbered.** |
| 2 | `platform` | enum | yes | `facebook` \| `youtube` \| `reddit` \| `x` | Source platform. |
| 3 | `source_page` | string | yes | slug | Canonical account slug, e.g. `dost_pagasa`. |
| 4 | `source_page_name` | string | yes | free text | Display name as captured. |
| 5 | `agency_id` | string | yes | slug | **Foreign key** into `government_agencies.csv`, e.g. `dost_pagasa`. Canonical ID for the Philippine government entity. |
| 6 | `agency` | string | yes | free text | Philippine national government agency, full name. Denormalized copy of `government_agencies.csv.agency_name`. |
| 7 | `agency_abbr` | string | yes | free text | e.g. `DOST-PAGASA`. Denormalized copy of `government_agencies.csv.agency_abbr`. |
| 8 | `post_id` | string | yes | platform id or `sha1(permalink)` | Foreign key into `posts_v1.csv`. |
| 9 | `post_url` | string | yes | URL | Public permalink of the parent post. |
| 10 | `post_date` | date | yes | `YYYY-MM-DD` | Publication date of the post. |
| 11 | `post_text` | string | yes | free text (may be empty) | **Verbatim** post caption/body. **Post context.** |
| 12 | `post_media_type` | enum | yes | `text` \| `image` \| `video` \| `mixed` \| `link` \| `unknown` | Post media type. **Post context.** |
| 13 | `post_topic` | string | no | slug | Manual topical tag by the collector, e.g. `flood_control`, `class_scheduling`, `vaccination`. Used for stratification and reporting. |
| 14 | `is_reply` | bool | yes | `true` \| `false` | Comment is a reply to another comment. |
| 15 | `parent_comment_id` | string | no | `comment_id` or empty | Empty when `is_reply == false`. |
| 16 | `parent_comment_text` | string | no | verbatim, may be empty | **Parent comment context** — verbatim parent comment text, if available. |
| 17 | `comment_text` | string | yes | verbatim | **The comment exactly as captured.** Original casing, emoji, typos, code-switching, punctuation — all preserved. Never edited. |
| 18 | `comment_text_norm` | string | yes | normalized | Normalized comment text (§6.2). **This is the primary modeling text field.** |
| 19 | `context_text_norm` | string | yes | normalized | Post + parent context, normalized (§6.3). Empty string if no context. **Annotation aid + optional robustness analysis, not the primary modeling field.** |
| 20 | `dedup_key` | string | yes | normalized | Exact-duplicate detection key (§7.1). |
| 21 | `n_tokens` | int | yes | ≥ 1 | Whitespace-token count of `comment_text_norm`. |
| 22 | `language` | enum | yes | `fil` \| `eng` \| `mixed` | Language of the comment. `other` is **excluded** (X_LANG), not labeled. |
| 23 | `label` | int | yes | `1` \| `0` | **1 = actionable suggestion/request, 0 = other comment.** (§10.1) |
| 24 | `label_str` | string | yes | `actionable` \| `other` | Human-readable mirror of `label`. Must always agree with `label`. |
| 25 | `annotator_id` | string | yes | `A1`–`A6` | Pseudonymous annotator. No names. |
| 26 | `label_2` | int | no | `1` \| `0` \| empty | Second annotator's label, when double-annotated. |
| 27 | `agreement` | bool | no | `true` \| `false` \| empty | `label == label_2`. Empty when `label_2` is empty. |
| 28 | `adjudicated_by` | string | no | `A1`–`A6` \| `ADVISOR` | Who resolved a disagreement. Empty if no disagreement. |
| 29 | `adjudication_note` | string | no | free text | One-line rationale for the resolution. Feeds the guidelines' edge-case bank. |
| 30 | `guideline_version` | string | yes | `v1.x` | Version of the annotation rules the label was produced under. |
| 31 | `source_snapshot` | string | yes | run id | `run_id` of the collection run that produced the row (§3.3). |
| 32 | `collected_at` | string | yes | ISO 8601 | Capture timestamp. |
| 33 | `pii_redacted` | bool | yes | `true` \| `false` | Whether anonymization altered this row. |
| 34 | `split` | string | yes | `train` \| `dev` \| `test` | Mirrors `splits/*.csv`. **The split files are authoritative**; this column is a convenience copy and must match. |
| 35 | `notes` | string | no | free text | Free-text row-level note (rarely used). |

**Column groups and who owns them**

- `1–17`, `19–22`, `31–33` → **producer-owned** (Member 4). Member 5 consumes, does not modify.
- `23–30` → **annotation-owned** (Member 4 + annotator team).
- `18`, `34` → **producer-owned**, but Member 5 may regenerate `comment_text_norm` under its own vectorizer (lowercasing, tokenization) — see §6.4.
- `18` **must not** be lowercased, punctuation-stripped, or emoji-removed in the shipped file. Those are Member 5's vectorizer decisions.

### 5.3 `posts_v1.csv` columns

`post_id`, `platform`, `source_page`, `source_page_name`, `agency_id`, `agency`, `agency_abbr`, `post_url`, `post_date`, `post_text`, `post_media_type`, `post_topic`, `source_snapshot`, `collected_at`, `n_comments`

**Invariant:** the denormalized post fields in `dataset_v1.csv` (`post_url`, `post_date`, `post_text`, `post_media_type`) **must be byte-identical** to the corresponding row in `posts_v1.csv`. `tools/validate_dataset.py` checks this (check V-07).

### 5.4 `splits/*.csv` columns

`comment_id`, `split`, `platform`, `source_page`, `post_id`, `label`

Member 5 may join the split files to `dataset_v1.csv` on `comment_id` alone; the extra columns exist for auditing and for any subgroup reporting.

### 5.5 `dataset_v1.metadata.json` (required keys)

```jsonc
{
  "dataset_version": "v1",
  "created_at": "ISO8601",
  "producer": "M4",
  "guideline_version": "v1.0",
  "collection_window": { "start": "YYYY-MM-DD", "end": "YYYY-MM-DD" },
  "sources": [ { "platform": "...", "source_page": "...", "agency": "...", "collection_method": "..." } ],
  "n_raw_captured": 0,
  "n_excluded_by_reason": { "X_SPAM": 0 },
  "n_usable": 0,
  "class_counts": { "actionable": 0, "other": 0, "actionable_rate": 0.0 },
  "counts_by_platform": { "facebook": 0 },
  "counts_by_source_page": { "dost_pagasa": 0 },
  "counts_by_split": { "train": 0, "dev": 0, "test": 0 },
  "language_counts": { "fil": 0, "eng": 0, "mixed": 0 },
  "split_seed": 42,
  "split_strategy": "stratified by label, grouped by post_id",
  "agencies": [ { "agency_id": "...", "agency_name": "...", "agency_abbr": "...", "agency_type": "...", "parent_department": "...", "platform": "...", "source_page": "..." } ],
  "counts_by_agency": { "dost_pagasa": 0 },
  "lineage": {
    "n_raw_captured": 0,
    "n_extracted_to_interim": 0,
    "n_excluded_by_reason": { "X_SPAM": 0, "X_DUP_EXACT": 0, "X_DUP_NEAR": 0, "X_LANG": 0, "X_EMPTY": 0, "X_OFFICIAL": 0, "X_PII": 0 },
    "n_candidate_pool": 0,
    "n_labeled": 0,
    "n_usable_final": 0,
    "reconciles": true
  },
  "double_annotated_n": 0,
  "cohens_kappa": 0.0,
  "kappa_agreement_band": "substantial|almost perfect|...",
  "auto_annotator": { "used": true, "tool": "...", "version": "...", "gold_set_n": 0, "gold_macro_f1": 0.0, "gate_passed": true },
  "tool_versions": { "python": "3.x", "pandas": "x.y", "scikit-learn": "x.y" },
  "pii_scrub_patterns": ["..."]
}
```

### 5.6 Data lineage — raw → usable → final

Every comment in the delivered dataset can be traced back through a fixed chain of layers.
**Nothing is ever deleted or edited in place**; each layer is regenerated from the one above
it, and the row count at every step is recorded.

| # | Stage | Layer on disk | Input | Transformation | Output | Gate |
|---|---|---|---|---|---|---|
| 0 | **Capture** | `data/raw/<platform>/<source_page>/<run_id>.json` | Live platform API | Retrieve post + comment payloads **exactly as returned**. Nothing is filtered, renamed, or reformatted here. | Immutable raw snapshots | — |
| 1 | **Extract** | `data/interim/comments_captured.csv`, `posts_captured.csv` | Raw snapshots | Flatten each payload into one row per comment / one row per post. Verbatim text. Attach `agency_id` via the registry (§3.1b) and `post_id`. **No filtering at this stage.** | `n_extracted_to_interim` rows | — |
| 2 | **Clean** | `data/processed/` (candidate pool) | `interim/` | Exclusion rules (§4.2) → normalization (§6.2) → dedup (§7) → spam filters (§8) → PII scrub (§11). Every removal is written to the **exclusion ledger** with a reason code. | `n_candidate_pool` rows | **G2 — data freeze** |
| 3 | **Annotate** | `data/processed/dataset_v1.csv` | Candidate pool | Labeling under `docs/ANNOTATION_GUIDELINES.md`. 100% single-pass + 20% double-annotated + adjudication. Labels and `guideline_version` attached. | `n_labeled` rows | — |
| 4 | **Split** | `data/processed/splits/` | Labeled dataset | Stratified by label, grouped by `post_id`, seed 42. 70/15/15. | `train` / `dev` / `test` | — |
| 5 | **Validate & freeze** | `dataset_v1.metadata.json`, `validation_report.txt` | Everything above | Run `tools/validate_dataset.py` (V-01…V-16). Write the lineage reconciliation and the metadata file. | **Final deliverable** | **G3 — label freeze** |

**The row-count reconciliation is mandatory.** This identity must hold and is checked by
`tools/validate_dataset.py` (check V-16):

```
n_raw_captured
  = n_extracted_to_interim
  = n_candidate_pool + Σ(n_excluded_by_reason.values())
  = n_labeled
  = n_usable_final
  = counts_by_split.train + counts_by_split.dev + counts_by_split.test
```

If any row cannot be accounted for, it is a bug, not a rounding difference. The final line
of this reconciliation, `n_usable_final`, is the number that fills the paper's `<number>`
placeholder in the Scope section.

**Which layer answers which question**

| Question | Answered by |
|---|---|
| "What exactly did the platform return?" | `data/raw/` |
| "What did we collect before making any judgment calls?" | `data/interim/` |
| "What was removed, and why?" | The exclusion ledger (reason codes in §4.2) and `lineage.n_excluded_by_reason` in the metadata |
| "What is the labeled dataset a consumer should load?" | `data/processed/dataset_v1.csv` |
| "Which rows go in which split?" | `data/processed/splits/*.csv` |
| "Which government agency does this row come from?" | `agency_id` → `data/provenance/government_agencies.csv` |
| "Which post was it on?" | `post_id` → `data/processed/posts_v1.csv` |

---

## 6. Text processing contract

### 6.1 Two-level text policy

| Level | Field | Mutability |
|---|---|---|
| **L0 — Verbatim** | `comment_text`, `post_text`, `parent_comment_text` | Never edited by anyone. The archival ground truth. |
| **L1 — Normalized** | `comment_text_norm`, `context_text_norm` | Produced once by Member 4 under the rules below, then immutable. |
| **L2 — Model-internal** | vectorizer output | Member 5's territory: lowercasing, tokenization, stopwords, n-grams. |

### 6.2 Normalization rules (L0 → L1), applied in this exact order

1. Unicode **NFC** normalization.
2. Remove zero-width and bidi control characters (`U+200B–U+200F`, `U+202A–U+202E`, `U+FEFF`).
3. Replace every URL with the literal token `<URL>`.
4. Replace every `@mention` with the literal token `<USER>`.
5. Replace every phone-number-like sequence with `<PHONE>`.
6. Replace every email address with `<EMAIL>`.
7. Replace every digit sequence of length ≥ 4 with `<NUM>` (house numbers, IDs, dates) — **but keep digits inside known measure phrases intact**? No: keep it simple and deterministic — **all digit runs of length ≥ 4 → `<NUM>`**; runs of length 1–3 are kept.
8. Collapse all runs of whitespace into a single space; strip leading/trailing whitespace.
9. **Keep** original casing, punctuation, and emoji.

> **Casing and punctuation are deliberately retained in L1.** Lowercasing would destroy the distinction between sentence-initial *Please* and mid-sentence *please* for no benefit, and the pipeline's regexes for feature extraction are specified case-insensitively (§6.5). Emojis are retained because they carry sentiment and request intensity in this corpus, and because removing them would be an unrecorded lossy transform.

### 6.3 Post context assembly

`context_text_norm` is built as:

```
context_text_norm = "[POST] " + norm(post_text) + " [COMMENT_PARENT] " + norm(parent_comment_text)
```

- If `post_text` is empty → the `[POST] ` segment is dropped entirely (not left as an empty bracket).
- If `is_reply == false` or the parent text is unavailable → the `[COMMENT_PARENT]` segment is dropped.
- The same normalization rules from §6.2 apply to post and parent text.
- **`context_text_norm` is never used as the primary modeling input** (§6.4).

### 6.4 Which text the models use (binding)

> **Member 5's two models in the paper are trained on `comment_text_norm` only.** Post context is **not** concatenated into the feature space for the primary comparison.

Rationale: the RQ compares *text-based TF-IDF* vs. *the same text plus linguistic features*. Injecting post context would introduce a third, unreported variable and would conflate the contribution of the linguistic features with the contribution of context. Context is delivered for two legitimate secondary uses:

- **Annotation quality** — annotators see the post when labeling (mandatory, §10.5), because many comments are uninterpretable without it ("Aba! Tama yan.").
- **Documented robustness analysis** (optional, clearly labeled as such): re-run the comparison with `context_text_norm` appended, reported separately in a subsection, never in place of the primary result.

### 6.5 Feature-extraction ownership

Member 5 owns feature extraction. The contract constrains it only where cross-team consistency matters:

- Feature regexes (e.g., for `please`, `dapat`, `sana`, `paki-`) are **case-insensitive** and operate on `comment_text_norm`.
- The feature list and its regexes are **frozen and published** in `docs/FEATURES.md` (owner: Member 5) before the final training run, and the same list is used for both models.
- Member 5 may **not** introduce features that are derived from `label` or from annotator behavior. Feature engineering informed by the gold set is permitted but must be disclosed.
- If Member 4 changes `comment_text_norm` after G2, Member 5 must re-verify the features; the contract records the `comment_text_norm` version in `dataset_v1.metadata.json` (`text_norm_version`).

### 6.6 `dedup_key`

```
dedup_key = lowercase( strip_all_non_alphanumeric( NFC(comment_text) ) )
```

with internal whitespace runs collapsed to one space. Emoji-only and punctuation-only comments yield an empty `dedup_key` and are excluded as `X_EMPTY` before dedup. `dedup_key` is a **technical key only** and is not used as modeling text.

---

## 7. Deduplication rules

### 7.1 Exact duplicates

Two comments are **exact duplicates** if `dedup_key` is equal and non-empty.

**Rule:** retain the **earliest captured** occurrence (tie-break by `collected_at`, then by `comment_id`), drop the rest with reason `X_DUP_EXACT`.

Rationale for keeping the earliest: it preserves the original thread context and the most conservative timestamp.

> **Cross-post duplicates:** the same text posted on two different posts of the same account is still an exact duplicate by this definition and will be dropped. This is intentional (it is a repeated complaint, not independent evidence) and the count is reported.

### 7.2 Near-duplicates

Two comments are **near-duplicates** if, after `dedup_key` normalization, one is a substring of the other **and** the shorter has ≥ 5 tokens, **or** their token-level Jaccard similarity ≥ 0.90.

**Rule:** within each `(source_page)` group, retain the **longer** comment (more information) and drop the shorter with reason `X_DUP_NEAR`. Additionally, cap the number of retained near-identical comments from the same account on the same post at 2.

Rationale: exact-dedup alone leaves template spammers ("Good morning sir/ma'am, please approve my pending request 🙏") massively over-represented, which would inflate the `actionable` class and let a model trivially learn templates.

### 7.3 Ordering guarantee

**All deduplication happens before the train/dev/test split.** If a duplicate pair is split across train and test, the model is evaluated on text it has seen. §12.4 makes this a hard validation check.

---

## 8. Spam, low-value, and automated-content filters

Filters are **deterministic rules** applied in order; each rule is logged with its hit count. All filters are applied to the **normalized** text.

| Rule | Condition | Reason code |
|---|---|---|
| F1 | Contains a phone number, email, or external URL **and** promotional markers (`job`, `hiring`, `promo code`, `discount`, `click here`, `DM me`, `sale`, `investment`, `crypto`, `mlm`, `loan`, ` earn `, `online business`, `shopee`, `lazada`, `telegram`) | `X_SPAM` |
| F2 | Contains the same URL in ≥ 3 comments from the same account in the candidate pool (account-level spam burst) | `X_SPAM` |
| F3 | Matches a commercial/registration regex set (e.g. `https?://(bit\.ly|tinyurl|linktr\.ee|t\.me|wa\.me)/`, `add me on fb`, `gcash`, `codash`, `opengov`) | `X_SPAM` |
| F4 | ≥ 60% of characters are the same repeated character, or the text is a single repeated token (e.g. `aaaaaaaaaaaaaaaa`, `hahaha`, `HAHA`) | `X_SPAM` |
| F5 | Contains an emoji-only reaction string with no word token (`X_EMPTY` catches most; this catches mixed-emoji padding) | `X_SPAM` |
| F6 | Account-level burst: ≥ 5 candidate comments from the same account on the same post with ≥ 0.85 mutual token Jaccard | `X_SPAM` |
| F7 | Requests that are **purely commercial personal business** unrelated to the agency's mandate (e.g., "kayo ba may ganit na product sa inyo?") — **manual review by the collector, logged individually** | `X_SPAM` |
| F8 | Duplicate comments copied from another platform's announcement (verbatim repost of the agency's own announcement text) — manual review, logged | `X_SPAM` |

**Filters F1–F6 are automatic. F7–F8 are manual, logged per row, and every manual removal is re-checked by a second team member.** The manual removal count is reported.

> **Do NOT filter on sentiment, on profanity, on political content, or on length (beyond `X_EMPTY`).** Aggressive "quality" filtering is the most common way a dataset like this silently loses its negative and non-actionable classes. If in doubt, keep the row.

---

## 9. Class balance and dataset composition

| Metric | Target |
|---|---|
| Minimum total usable comments | **1,000** (combined platforms) |
| Minimum primary (Facebook) usable comments | **600** |
| `actionable` class | **≥ 15%** and **≤ 65%** of the dataset. Below 15% → switch to stratified collection (§3.4). Above 65% → additional non-request posts should be sampled to restore balance, and the natural prior is reported. |
| Minimum per-class count | **≥ 150** in the primary dataset |
| Per-source-page minimum | **≥ 40** usable comments per source page (so no single page dominates and no page is a statistical singleton) |
| Per-language coverage | Filipino, English, and mixed **all ≥ 10%** of the dataset |

**Reporting requirement:** the **natural class prior** (the actionable rate in the unmanipulated collection) is reported alongside the final rate, so the paper can state whether balance was achieved by natural distribution or by stratified sampling. If stratified sampling was used, evaluation must also report **precision, recall, and F1 on the natural-prior-weighted test set** or state the sampling design and any reweighting applied — Member 5's decision, documented in the paper.

---

## 10. Annotation contract

Full rules: `docs/ANNOTATION_GUIDELINES.md`. This section states only the parts that affect the interface.

### 10.1 Label encoding

- `label = 1` → **actionable suggestion/request**
- `label = 0` → **other comment**
- `label_str` mirrors `label` exactly: `"actionable"` / `"other"`.
- **Member 5 must set `pos_label=1`** in all metric calls (`sklearn.metrics.classification_report(..., pos_label=1)`, `f1_score(y_true, y_pred, pos_label=1)`, `confusion_matrix(..., labels=[0,1])`). A flipped `pos_label` silently inverts every reported metric and would invalidate the paper's conclusion.
- The confusion matrix is reported with **rows = true, columns = predicted**, in the order `[[TN, FP], [FN, TP]]` for `labels=[0, 1]`.

### 10.2 Labels are one-per-comment, multi-label is not permitted

A comment proposing three actions is still **one** comment with `label = 1`. There is no action-count column, no multi-hot encoding.

### 10.3 Who annotates

| Role | Who | Scope |
|---|---|---|
| Primary annotator | Member 4 (M4) + assigned teammates | 100% of the dataset |
| Second annotator | ≥ 1 teammate, not the primary annotator of that row | **20% minimum of rows, stratified by class and source page** (≥ 200 rows for a 1,000-row dataset) |
| Adjudicator | Member 4, escalating to the adviser | 100% of disagreements |
| Gold-set annotators | 2 annotators + adjudication | 120 rows (see §10.6) |

### 10.4 Language tagging

`language` ∈ {`fil`, `eng`, `mixed`}:
- `fil` — predominantly Filipino/Tagalog.
- `eng` — predominantly English.
- `mixed` — both present in meaningful proportion (a code-switched comment). **This is the study's core population and must not be under-represented.** Code-switching is common even in comments tagged `fil` ("Sana maayos ang kalsada, please fix it") — tag the *predominant* language, and note that `mixed` is the most policy-relevant stratum for reporting.
- Comments in other languages are excluded at cleaning (`X_LANG`) and **never** receive `language = other`.

### 10.5 Annotation must be performed with post context visible

Annotators work in a labeling tool (Label Studio / Doccano / a local CSV viewer — Member 4's choice) that displays, for every comment: the **post text**, the **post date**, the **source agency**, and — for replies — the **parent comment text**.

This is mandatory: a large fraction of replies ("Aba! Tama yan.", "Same, please fix ours too.") are unlabelable without the post. The labeling interface must show context; annotators must not label from the comment alone.

Annotators **must not** see `label`, `label_2`, `agreement`, or `adjudicated_by` while labeling (the tool hides annotation columns).

### 10.6 Agreement measurement

- Compute **Cohen's kappa** on the double-annotated subset (20% minimum).
- Interpretation band (Landis & Koch 1977): `< 0.20` slight · `0.21–0.40` fair · `0.41–0.60` moderate · `0.61–0.80` substantial · `0.81–1.00` almost perfect.
- **Gate: κ ≥ 0.60.** If the gate fails:
  1. Review the disagreement set and the guidelines' edge-case bank.
  2. Amend the guidelines → bump `guideline_version` (e.g. `v1.0` → `v1.1`) with a changelog entry.
  3. **Re-annotate the full dataset under the new version.** Labels produced under a superseded guideline version are not mixed into the final set.
  4. Recompute κ. If still < 0.60 after one revision, escalate to the adviser and consider an objective/task-definition revision.
- Report κ, the confusion breakdown of disagreements, and the number of adjudicated rows in the paper (Member 6) and in `dataset_v1.metadata.json`.

### 10.7 Auto-annotation assistant (optional, gated)

`docs/NLP-PLAN.pdf` permits using an accurate auto-annotator. It is permitted **only** under this policy:

**Stage 1 — Gold set.** 120 rows, double-annotated and adjudicated by two human annotators under `v1.0` guidelines. Composition: 60 rows with high likelihood of `actionable`, 60 with high likelihood of `other`, drawn across platforms and source pages, **sampled from the cleaned pool by the collector using the §8 filters — never cherry-picked to favor the assistant.**

**Stage 2 — Evaluation.** Run the candidate assistant on the gold set. Record macro-F1 and Cohen's kappa against gold.

**Stage 3 — Gate.** The assistant may be used **only if** `macro-F1 ≥ 0.80` **and** `kappa ≥ 0.60` on the gold set.

**Stage 4 — Permitted use.** As a **pre-labeling triage assistant only**:
- The assistant produces **draft** labels.
- **Every** draft label is confirmed or corrected by a human annotator before it enters `label`.
- **No assistant-produced label may be used as a second annotator's label**, and assistant-labeled rows may **not** be included in the κ computation. This prevents circularity in the agreement measurement.
- The assistant may also be used to **order** the labeling queue (most-uncertain first), which does not affect label content.

**Stage 5 — Disclosure.** If the assistant was used, the paper's Methodology **must** state: the tool and version, the gold-set size, the gate metrics, the proportion of rows pre-labeled, and the human-verification rate (target: 100%). Member 6 owns that text; Member 4 supplies the numbers.

**Stage 6 — Failure is a valid result.** If the gate fails, the assistant is not used, and the attempt + its metrics are recorded in `dataset_v1.metadata.json` (`auto_annotator.gate_passed = false`) and may be reported as a negative result.

**Constraint:** prefer **local / offline** assistants. If a hosted assistant is used, send only `comment_text_norm` after the PII scrub (§11) — never `post_text`, and never the raw snapshot — and record the provider and version in the metadata.

### 10.8 Annotation trace

Every label carries: `annotator_id`, `label_2`, `agreement`, `adjudicated_by`, `adjudication_note`, `guideline_version`. This makes every label traceable to a rule version and a decision, which is what makes the dataset defensible in review.

---

## 11. Anonymization (PII scrub)

### 11.1 What is removed

| Category | Action |
|---|---|
| Usernames / display names | Removed. No commenter's name or handle appears in any delivered artifact. |
| Profile links, `@mentions` | Replaced with `<USER>` in L1 text; the original handle is **never** stored in the processed dataset. |
| Profile URLs, IDs, `comment_id` of the author | Never collected. |
| Phone numbers | Replaced with `<PHONE>`. |
| Emails | Replaced with `<EMAIL>`. |
| Government ID numbers, birthdates, addresses, plate numbers | Replaced with `<NUM>` or removed; if a comment is *dominated* by such data, the row is excluded as `X_PII`. |
| URLs | Replaced with `<URL>` in L1; the raw permalink is retained **only** in the internal raw snapshot and in `posts_v1.csv` (public post, not personal data). |
| Geolocation details naming a private individual's residence | Removed where identifiable. |

### 11.2 What is retained

- The **verbatim comment text** in the internal `data/interim/` layer may contain names until scrubbing runs. `data/interim/` and `data/raw/` are **internal-only, gitignored, never published**. Only `data/processed/` is publishable.
- `pii_redacted` records whether the row was altered.
- Every processed row's text must pass a **final automated PII scan** before delivery; any residual hit blocks the release until manually reviewed.

### 11.3 Rules

- **No re-identification.** Do not use handles, profile photos, or posting patterns to try to identify commenters. Do not cross-reference comments with voter lists, phone directories, or any other personal-data source.
- **The unit of analysis is the comment, not the person.** No per-commenter statistics.
- **Aggregated reporting only.** Published tables report dataset-level and source-page-level aggregates.

---

## 12. Scope limits the dataset cannot support

The dataset supports claims about **the detectability of actionable suggestions in public comments** and nothing more. It does **not** support claims about government responsiveness, policy outcomes, public satisfaction, or the quality of government services.

This mirrors the Scope section of `docs/NLP-Final-Paper.pdf`. Any wording in the write-up that exceeds this is a scope error.

---

## 13. Repository and artifact layout

```
nlp-data/
├── DATA_CONTRACT.md                  ← this document
├── docs/
│   ├── NLP-PLAN.pdf
│   ├── NLP-Final-Paper.pdf
│   ├── ANNOTATION_GUIDELINES.md      ← D-01, companion to §10
│   ├── DATA_CARD.md                  ← D-09
│   ├── FEATURES.md                   ← owned by M5 (§6.5)
│   └── COLLECTION_PROTOCOL.md        ← per-source collection detail (§3.3)
├── data/
│   ├── raw/                          ← IMMUTABLE snapshots, gitignored
│   │   └── <platform>/<source_page>/<run_id>.json
│   ├── interim/                      ← gitignored, internal only
│   │   ├── comments_captured.csv
│   │   └── posts_captured.csv
│   ├── processed/                    ← publishable
│   │   ├── dataset_v1.csv
│   │   ├── dataset_v1_ext.csv
│   │   ├── posts_v1.csv
│   │   ├── dataset_v1.metadata.json
│   │   └── splits/{train,dev,test}.csv
│   └── provenance/                   ← gitignored? No — committed (small, non-personal)
│       ├── government_agencies.csv   ← canonical PH government agency registry
│       ├── government_agencies.csv
│       └── collection_log.csv
├── src/
│   ├── collect/{facebook,youtube,reddit}.py
│   ├── clean/{dedup.py, spam.py, pii.py, normalize.py}
│   ├── annotate/{tool_setup.md, agreement.py}
│   └── validate/validate_dataset.py
└── tools/
    └── validate_dataset.py            ← D-08, the acceptance test
```

**Version control:** the repository is currently **not** a git repository. **Initialize git** (`git init`), commit `docs/`, `DATA_CONTRACT.md`, `src/`, `tools/`, and `data/processed/` + `data/provenance/`. Add `.gitignore` entries for `data/raw/` and `data/interim/`. Use Git LFS only if a processed file exceeds 5 MB (it should not: ~1,000 rows of short text).

---

## 14. Validation and acceptance criteria (Member 5's pre-flight check)

`tools/validate_dataset.py` must pass with **0 errors** before Member 5 begins modeling. Checks:

| ID | Check |
|---|---|
| V-01 | File exists, UTF-8, parseable CSV, header exactly matches §5.2 column order. |
| V-02 | Row count ≥ 1,000 (or ≥ 600 for the Facebook-only primary set), and the metadata row count equals the CSV row count. |
| V-03 | `comment_id` unique, non-null, and matches `^[a-z]+_[a-z0-9_]+_\d{4}$`. |
| V-04 | `label` ∈ {0,1} and `label_str` agrees with `label` on **every** row. |
| V-05 | `language` ∈ {fil, eng, mixed}; `platform` ∈ {facebook, youtube, reddit, x}; `is_reply`/`agreement`/`pii_redacted` are `true`/`false`. |
| V-06 | `label_2` is either empty or ∈ {0,1}; `agreement` is empty exactly when `label_2` is empty, and `true` exactly when `label == label_2`. |
| V-07 | Every `post_id` exists in `posts_v1.csv`, and the denormalized post fields match exactly. |
| V-08 | `comment_text_norm` is non-empty, has no zero-width characters, contains no URL/email/phone regex match (PII leak check). |
| V-09 | `dedup_key` values are unique across the dataset (no residual exact duplicates). |
| V-10 | `split` values ∈ {train, dev, test}; the `split` column agrees with the `splits/*.csv` files; every `comment_id` appears in exactly one split file; counts match the metadata. |
| V-11 | **No leakage:** no `dedup_key` appears in more than one split; no `post_id` appears in more than one split (post-level grouping held). |
| V-12 | Class counts: `actionable` ≥ 150, `other` ≥ 150, actionable rate within [0.15, 0.65]. |
| V-13 | No `comment_text_norm` value is empty; `n_tokens` matches `len(comment_text_norm.split())`. |
| V-14 | The metadata JSON parses and contains every key listed in §5.5. |
| V-15 | The class prior in the test split is within ±10 percentage points of the train split prior. |
| V-16 | **Lineage & agency integrity:** every `agency_id` in `dataset_v1.csv` and `posts_v1.csv` exists in `government_agencies.csv`; the denormalized `agency` and `agency_abbr` match the registry exactly; the row-count reconciliation in §5.6 holds (`n_raw_captured = Σ exclusions + n_candidate_pool = n_labeled = n_usable_final = Σ split counts`); `lineage.reconciles == true` in the metadata. |

**Acceptance:** Member 4 declares the dataset delivered when V-01…V-15 pass and the report is stored at `data/processed/validation_report.txt`. Member 5 confirms receipt and acceptance, or raises specific failed checks.

---

## 15. Delivery schedule (Member 4)

| # | Milestone | Output | Depends on |
|---|---|---|---|
| M1 | Decisions D-1…D-6 settled | Signed section in this contract | Adviser + team |
| M2 | **G1 schema freeze** | This contract v1.0 | M1 |
| M3 | Source list frozen; collection protocol documented | `government_agencies.csv`, `COLLECTION_PROTOCOL.md` | M2 + adviser sign-off |
| M4 | Collection pilot (2 pages, 2 posts each) | raw snapshot + yield estimate | M3 |
| M5 | Full collection | raw snapshots, `collection_log.csv`, `comments_captured.csv` | M4 |
| M6 | Cleaning + dedup + PII scrub | `interim/` → candidate pool | M5 |
| M7 | **G2 data freeze** | candidate pool + exclusion ledger | M6 |
| M8 | Gold set (120 rows) double-annotated; κ computed | gold set, κ | M7 + `ANNOTATION_GUIDELINES.md` v1.0 |
| M9 | Auto-annotator gate test (if a candidate exists) | gate metrics | M8 |
| M10 | Full annotation + adjudication | `dataset_v1.csv` with labels | M8/M9 |
| M11 | **G3 label freeze**; splits generated; metadata written | splits, metadata | M10 |
| M12 | Validation passes; DATA_CARD written; hand-off | `validation_report.txt`, `DATA_CARD.md` | M11 |
| M13 | Usable-comment count delivered to M6 for the paper's `<number>` | number + breakdown table | M12 |

Proposed calendar (AY 2026–2027): M1–M3 in week 1–2; M4 in week 3; M5–M7 in weeks 3–5; M8–M10 in weeks 5–8 (annotation is the long pole — start it as early as possible); M11–M13 in weeks 8–9.

---

## 16. Change control

1. **Every change to this document is a numbered version bump** with a dated changelog entry in §17.
2. **Changes to §4–§6 (schema, rules, interface) after G1 require the adviser's approval** and a note to Member 5 before any dependent work proceeds.
3. **Changes to §10–§12 (annotation, agreement, scope limits) after G3 require re-annotation** of affected rows and a metadata bump.
4. **Emergency changes** (e.g., a platform blocks collection mid-study) are allowed with a same-day changelog entry and notification to Members 5 and 6.
5. **Never** change a label, a split assignment, or `comment_id` silently. Corrections happen in a new version with a recorded reason.
6. `guideline_version`, `dataset_version`, and `text_norm_version` are recorded in the metadata so any row can be traced to the exact ruleset that produced it.

---

## 17. Changelog

| Version | Date | Author | Change |
|---|---|---|---|
| `1.0-draft` | 2026-10-20 | M4 (MALASAN) | Initial contract drafted from `NLP-PLAN.pdf` and `NLP-Final-Paper.pdf`. Schema, dedup/spam/PII rules, annotation interface, splits, validation, schedule. |
| `1.1-draft` | 2026-10-20 | M4 (MALASAN) | Switched collection to keyless HTML/DOM scraping: rewrote §3.2 routes and §3.3 run parameters, replaced the `collection_method` enum, dropped the credentials and `.env` requirement. Removed §12 (legal/ethical/platform-compliance); §12 is now the dataset's scope limits. README and requirements updated. |

---

## 18. Open decisions (must be closed before G1)

| ID | Decision | Proposed default | Owner | Due |
|---|---|---|---|---|
| D-1 | Which source accounts/pages exactly? | 4–6 agencies across ≥ 2 domains (e.g., DOST-PAGASA, DSWD, DPWH, DepEd, DOH, DOST) | M4 + team | G1 |
| D-2 | Which platforms in scope, and is Facebook the primary dataset? | Facebook = primary (`dataset_v1.csv`); YouTube = extension; Reddit/X optional | Team + adviser | G1 |
| D-3 | Collection method sign-off | Headless-DOM collection for Facebook, HTML/`ytInitialData` parse for YouTube, keyless JSON for Reddit, manual capture as fallback. Sign-off recorded in `COLLECTION_PROTOCOL.md` | Adviser | Before collection |
| D-4 | Annotator roster, second annotator, adjudicator | M4 primary; 1 teammate second-annotates ≥ 20%; M4 adjudicates | Team | G1 |
| D-5 | Auto-annotator candidate and hosting | Local/offline preferred; gate = macro-F1 ≥ 0.80 and κ ≥ 0.60 on a 120-row gold set | Team | M8 |
| D-6 | Labeling tool | Doccano or Label Studio (open source, supports context display and multi-annotator) | M4 | M8 |
| D-7 | Final usable-comment count for the paper's `<number>` | ≥ 1,000 combined; ≥ 600 Facebook-only | M4 | M13 |
| D-8 | Whether to release the dataset publicly (anonymized) | Recommended: yes, on request to the adviser, with a README and license | Adviser | M13 |
| D-9 | Whether a secondary "with context" robustness analysis is reported | Recommended: yes, as a clearly separate subsection | M5 + M6 | Before writing Results |
| D-10 | Natural vs. stratified class balance | Collect naturally; stratify only if actionable < 15% | M4 | M7 |

---

## Appendix A — Required example bank (pointer)

`docs/ANNOTATION_GUIDELINES.md` §5 contains the **canonical example bank** (≥ 30 labeled examples across platforms, languages, and edge cases). Every edge case that required adjudication must be added to that bank with its label and rationale, and the bank is versioned with the guidelines. The example bank is Appendix material for the paper.

## Appendix B — Quick reference: the six things Member 5 must not assume

1. That `label` might be flipped — it is not. `1 = actionable`. Use `pos_label=1`.
2. That `comment_text` is lowercase or stripped — it is not. `comment_text` is verbatim; `comment_text_norm` is lightly normalized only.
3. That a missing `label_2` means a bad row — it means "not double-annotated".
4. That `post_text` is part of the model's input — it is not, for the primary comparison.
5. That the dataset is Facebook-only — `dataset_v1.csv` is; `dataset_v1_ext.csv` is not. Confirm which one you are using and say so in the paper.
6. That the split files are advisory — they are authoritative. Join on `comment_id`.
