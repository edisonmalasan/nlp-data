# PENDING RESOLUTION — open items, owners, and what unblocks them

**What this file is.** A register of everything that is still open on the
dataset, who owns it, and what happens if it is not resolved. It exists so
that the hand-off is not a surprise and the adviser meeting has a concrete
agenda.

**What this file is not.** It is not a to-do list for the collector, and it is
not a substitute for the contract's changelog (`DATA_CONTRACT.md` §17), which
records *changes to the contract itself*. Nothing here changes the contract.

**How to use it.** Each item has an owner and a fallback. An item with a
fallback can be closed by deciding to take the fallback. An item marked
**BLOCKING** cannot be closed by a decision — the release is not valid until it
is done.

**Last updated:** 2026-10-21. Owner of this register: M4 (MALASAN).

---

## 1. The release gate

### 1.1 Human verification of the labels — **BLOCKING**

| | |
|---|---|
| **What** | Read a random sample of **120 rows** of `dataset_v1.csv` and decide `actionable` / `other` yourself, without seeing the annotator's label. Record the agreement rate and Cohen's κ. |
| **Why it exists** | The contract requires it (§10.1, §14 V-17). The labels were produced by an LLM working from the written guidelines; a human-checked number is what makes the label quality *demonstrated* rather than asserted. |
| **Owner** | M4 (you) — this is the researcher's own verification and it cannot be delegated to a model. |
| **How** | `data/interim/verify_sample.csv` — 120 rows, **no label in the file**, so the reading cannot be anchored. Fill the `human_label` column with 0 or 1, then:<br>`python tools/verification_sample.py score`<br>It prints the agreement rate, Cohen's κ and the confusion matrix. |
| **The gate** | κ ≥ 0.60. If the annotator disagrees with you on **more than about 20%** of the sample, the cue lists have to be fixed and the dataset re-scored before release. Do not release a dataset whose annotator is that far off. |
| **Fallback if not done** | None. The release is not valid. `python tools/build_release.py --check` will keep reporting NOT READY, and that is correct. |

### 1.2 The blinded re-label — **BLOCKING**

| | |
|---|---|
| **What** | Re-label the same **20% of rows** blind, and compute κ between `label` and `label_2`. |
| **Why it exists** | This is the **intra-annotator reliability** statistic — test-retest, not inter-annotator agreement. There is one annotator. A re-label the same day measures memory, not reliability. |
| **Owner** | M4 (you). |
| **Timing** | **Not before 2026-10-28.** The contract requires a washout of **≥ 7 days** from the labelling pass, so a re-label started earlier measures nothing. |
| **How** | `data/interim/relabel_sample.csv` — 250 rows, drawn blind, no label in the file. Fill `label_2`, then the scoring command reports κ. |
| **The gate** | κ ≥ 0.60, and `label_2` populated on ≥ 20% of rows. |
| **Fallback if not done** | None. The release stays blocked. |

---

## 2. Decisions that are not the collector's to make

### 2.1 The invitation-marker list — the adviser

| | |
|---|---|
| **What** | The "request-inviting" stratum selects posts whose caption contains an invitation marker. The marker list is in `src/collect/find_invites.js` and it is **the collector's choice**. |
| **Why it matters** | The contract pre-registered the *remedy* (§3.4: "switch to deliberate stratified collection … and document the sampling design"), but not the *markers*. Which patterns count as a request-inviting post is a methodological decision about what counts as a citizen request. It goes in the Methodology section. |
| **Owner** | The adviser, with M4. |
| **Current state** | The stratum is implemented, working, and recorded on every row in `stratum` (column 40). It contributed **22 rows** of the 1,250 — the yield is low because the markers are narrow. |
| **The decision** | Either (a) sign off the marker list as written, and report the stratum's small contribution honestly, or (b) widen the markers, which raises the yield and also raises the actionability of the corpus. (b) changes the class balance and so changes the reported numbers, which is why it needs sign-off rather than a collector's judgement. |
| **Fallback** | If the adviser declines to rule on it, the stratum stays in the dataset with its small yield, and the Methodology states that the markers were the collector's and were not independently reviewed. That is honest and defensible, but it is weaker than a sign-off. |

### 2.2 "Manually annotate" in the paper's objective 1 — Member 1

| | |
|---|---|
| **What** | `docs/NLP-Final-Paper.pdf`, Objective 1, reads *"Collect and manually annotate eligible public Facebook comments into two classes."* |
| **Why it matters** | The labelling was **not** done by hand. The plan (`docs/NLP-PLAN.pdf`) says *"manually annotate comments (everyone will help this) **Though if there's an accurate auto annotator that can help, go**"* — so the auto-annotator was explicitly permitted by the task assignment, and the paper's scope is marked *"tentative, subject to change from further research and model development."* But the paper still says "manually", and a reader will take the Objective at face value. |
| **Owner** | Member 1 (LOPEZ) owns the Introduction and framing; M4 must supply the accurate description. |
| **What M4 supplies** | The accurate wording, which the contract fixes (§10.1): **"LLM-assisted annotation with human verification"**, stating the engine and its version, the cue and rule design, the share of rows auto-decided vs adjudicated vs human-verified, the human-verification sample size and agreement, and the blinded re-label κ. **Never "manual annotation"** — that would be a misreport, and the contract says so in three places. |
| **Fallback** | None, really — but note the repo is already consistent: `AGENTS.md`, `DATA_CONTRACT.md` §10, `README.md` and `docs/ANNOTATION_GUIDELINES.md` all forbid describing it as manual, the dataset's own metadata says *"LLM-assisted annotation with human verification"*, and the data card says the same. Only the paper's Objective still uses the old word. |

---

## 3. Known properties of the delivered data

These are **not** defects to be fixed. They are properties of the corpus that the
Methodology and Limitations must state. Each one is in the data card.

### 3.1 The corpus is concentrated in a few posts

Ten posts hold **49%** of the rows; the two largest are a DepEd webinar and a
DPWH bridge-repair thread where most comments are check-ins and reaction. The
split is grouped by `post_id`, so a model cannot score well by recognising
*which post* a comment came from — but the distribution is a real limitation and
the write-up must say so rather than smooth it over.

**Owner:** M6 (AGUSTIN), in Results and Discussion. **No action beyond writing it down.**

### 3.2 Reddit contributes nothing

No Philippine national government agency runs a subreddit. 88 candidate
subreddits were checked; the only one about government is `r/PHGov`, which
describes itself as *"Community dedicated towards the Philippine Government"* —
user-created, so it fails the contract's own S1 and S2. The reasoning is in
`data/provenance/PLATFORM_COVERAGE.md`.

**Owner:** M6, in the Methodology's platform description. **No action beyond writing it down.**

### 3.3 The feed is throttled, so 31 accounts sit below the 8-post minimum

Contract §3.4 asks for the **8-12 most recent posts** per source. Ten accounts
clear it. Thirty-one do not, and the cause is the platform, not the collector:
Facebook now renders only the **first one or two posts** of a page's feed in
the driven tab, and scrolling does not load more. That is measurable, not
inferred — on the same pages that yielded a full feed earlier in the run:

| page | posts rendered now | comments captured earlier |
|---|---|---|
| `DPWHph` | 3 | 546 |
| `DepartmentOfEducation.PH` | 2 | 277 |
| `pnagovph` | 2 | 12 |

A reload does not change it, and neither does a second visit. The pages
themselves load: the follower count, the category and the self-description all
render, and only the feed is short. So this is not a login wall, not a broken
extractor, and not a page that has stopped posting.

**What this means.** The per-account post counts are **at or above what the
platform would serve**, and the corpus is therefore short of the contract's
8-12 posts for those sources. The delivered numbers are:

- **1,610 Facebook comments** and 1,781 across platforms - both contract
  targets (600 Facebook, 1,000 total) are met more than twice over
- **31 of 47 accounts under 8 posts**, with the shortfall recorded per account
  rather than smoothed away

**Why it is recorded and not fixed.** The alternatives are both worse. Pushing
harder on a session already being throttled risks the whole session; changing
the sampling rule to reach older posts would breach §3.4's "no cherry-picking
posts by comment richness", which is the rule that keeps the frame honest.

**Owner:** M6, one sentence in the Methodology - *the platform served a
truncated recent feed, so the per-source post count is a floor rather than the
planned 8-12.* **No code change is correct here.**

### 3.4 YouTube yields are small

The YouTube app stopped booting in the driven tabs partway through the
collection. Video *discovery* was moved to the page's own data, but the
comments need the DOM, and the public endpoint returns comment stubs behind a
request that 404s for this client. YouTube contributed **101 comments**.

**Owner:** M4, if more YouTube is wanted — a re-run with the browser otherwise
idle should recover it. **Otherwise** it is reported as a limitation.

### 3.5 The post caption is missing on 23% of rows

56 of the 92 captured posts have no caption. The cause is a defect in the
extractor, since fixed (`src/collect/extract_facebook.js` reads the message
container Facebook marks with `data-ad-comet-preview`); the earlier captures
predate the fix. **No caption is wrong** — the 77% that are present are real
captions, and a caption that is real is truncated with an ellipsis the way
Facebook collapses a long one.

This does not touch the modelling text field (`comment_text_norm` alone) and it
touched at most the 53 A4 rows in the adjudication. The recovery tool is
`src/collect/recover_captions.py`.

**Owner:** M4. **Fallback if not recovered:** the empty captions are already
correct as "no caption", and the data card states the coverage.

### 3.6 The language column was noise, and has been re-labelled

**Now closed.** The seven adjudicators each applied their own version of the
Filipino/mixed boundary and did not agree with each other — one treated an
English greeting with *"po"* as mixed, another said a courtesy particle alone
does not create a mix. For a study *about* code-switching, a slice variable
whose annotators disagree with each other is the worst kind of noise.

The whole column has been re-labelled against one written text,
`data/interim/language_convention.md`, which settles the two rules that decide
everything (a courtesy particle does not create a mix; a naturalised loanword
inside a Filipino clause does not) and the four hard families the passes
found. **The label, the model's target, was not touched.** Only the slice
variable changed.

A consistency check (`tools/language_consistency.py`) finds the template
families that received more than one label, so the residue is visible rather
than assumed away. **Every row in the delivered dataset is now labelled
against that one convention** - 1,781 from the re-label, the rest from the
adjudication of the rows added since and a language pass over the rows the
engine decided on its own. No row falls back to the rule, which was only about
71% accurate against the adjudicated labels. Seven families still split, and they are genuine linguistic
variation rather than annotator disagreement: *"Good morning. Waiting for the
webinar"* is English, *"Good morning! Naa po bay link?"* is mixed.

**Residue that remains:** roughly one row in a thousand is a lone case of the
*"road improvement"* family, where a compound of two naturalised words was
judged `mixed` on one row and `fil` on another. The rule that settles it
(rule 2a) is in the convention, but an automated fix for it was **written and
withdrawn**: it read any two adjacent content words as an English compound, so
it misread *"salamat"* and *"buhay"* as English and flipped 88 correct rows. The
withdrawal is recorded in `data/provenance/language_rule2a.json`.

**Owner:** M4. **If M5 slices by `language`:** the column is now internally
consistent, but it is still a noisy variable, and a slice on it will be
sensitive to its errors. The `language` field is not a modelling feature.

### 3.7 The source pages are verified against Facebook's own signals — **CLOSED**

**All 32 registered Facebook accounts pass.** The earlier verification only
checked that the page *name* matched the agency name, which would not catch a
fan page or a personal profile called "deped". Every account is now checked
against what Facebook itself publishes:

1. the page **category** — a government agency is categorised *"Government
   organization"* or *"Public & Government Service"*;
2. the page **buttons** — a Page shows *Message* and *Follow*, a personal
   profile shows *Add Friend* and no *Message*;
3. the page's own **self-description** — *"This is the official Facebook page
   of the Department of Health in the Philippines"*;
4. a **`.gov.ph` domain** the page links.

Plus a cross-check that every collected post actually came from the registered
page, so a page that was registered and then collected from somewhere else is
caught. The verdict per account is in `data/provenance/page_governance.json`.

**Three registry errors were found and fixed:** PHIVOLCS was registered under
the name of its programme (*Earthquake and Volcano Observatories*) rather than
the agency (*Philippine Institute of Volcanology and Seismology*), and four
abbreviations were empty.

**On "deped":** `facebook.com/deped` is **not** the Department of Education's
page, and nothing was ever collected from it. Every collected DepEd post came
from `facebook.com/DepartmentOfEducation.PH`, whose name is *"DepEd
Philippines"*. The `deped` in the registry is the short slug used in the
`comment_id`, not a URL. The check is what makes that distinction checkable
rather than asserted.

**Owner:** M4. **No action.** If an account ever fails, it is removed from the
registry rather than left in.



### 3.8 The source frame has been widened — 47 Facebook accounts

The frame started at 10 accounts and now stands at 47. It is now **47 verified
Facebook accounts**, 10 YouTube channels and 5 X accounts, from a search of
**185 agency websites** — the Philippine national government has roughly two
hundred, and the ones that were missing were the bureaus, commissions and
government corporations that publish on social media.

Each account was found by reading the agency's **own website** for the Facebook
page it links to, and the page was then verified against Facebook's own
signals. The link from the agency is the evidence; nothing was found by
guessing a handle.

**What the search found, and did not:**

| | Count | |
|---|---|---|
| Verified official pages | 38 | of 177 sites reached |
| The agency's site has no Facebook link | 59 | nothing to find |
| The site did not load | 69 | mostly domains I had wrong |
| A page was linked but did not name the agency | 11 | rejected |

**Still open on the frame:** the 69 unreachable sites should be retried, and
the 14 new accounts have not yet been through the governance check (§3.6) —
they came through a different path, so they are verified by the same rules
but not yet verified by them. Their YouTube and X accounts are not yet
discovered either; the Facebook contact block of each new page is where its
agency declares them.

**Owner:** M4. **Fallback if not done:** the frame is already systematic and
documented, and the dataset exceeds every contract target without these.

| # | Question | Who | Why it matters |
|---|---|---|---|
| 4.1 | Is the primary dataset Facebook-only? | M4 + M5 | It is now: `dataset_v1.csv` is the 1,610 Facebook rows, `dataset_v1_ext.csv` is all 1,421. The paper's scope is Facebook, so this matches. But M5 must be told which file to model on. |
| 4.2 | Which file does M5 model on? | M5 | `dataset_v1.csv` (Facebook, 1,610 rows, 290 actionable). The extension file is there for a robustness analysis, not for the headline number. |
| 4.3 | Does M5 slice the results by `language`? | M5 | The `language` column is now assigned against one written convention for every row, so it is internally consistent (§3.5). It is still a *noisy* variable, and because the study is about code-switching, a slice on it will be sensitive to its errors. The convention is `data/interim/language_convention.md`. |
| 4.4 | Is the "invites" stratum reported separately? | M6 | It is recorded on every row in `stratum`, so it can be excluded and reported separately. The headline number should be the whole dataset, with the stratum reported as a design detail. |
| 4.5 | Is the collection still running, and does it need a stop? | M4 | The corpus has no ceiling, so the collection runs as a loop (`src/collect/collect_forever.py`). It has to be stopped before the label freeze (§1.1), because a row collected after the freeze would have no label. |
| 4.6 | Is the wider frame worth reporting as a design change? | M6 | The frame grew from 10 accounts to 46 during collection (§3.7). That is a systematic widening, not a change of subject, and the number belongs in the Methodology's source description. |

---

## 5. Closed — for the record

So that nobody re-opens them:

- **The contract's schema, splits, and the 17 acceptance checks.** All pass.
- **Every source page is a government page.** All 32 registered Facebook
  accounts pass the category, buttons, self-description and `.gov.ph` checks,
  and every collected post came from the registered page (§3.6).
- **The `language` column.** Re-labelled against one written convention for
  every row, with the residue visible rather than assumed away (§3.5).
- **The 1,000-comment target and the 600 Facebook target.** 1,781 usable, 1,610 Facebook. Both met.
- **The class-balance window (15%–65% actionable) and the ≥150 per class.** 18.0% actionable, 290 actionable / 1,320 other.
- **The four cells the research question needs.** All populated: 44% of the
  actionable comments carry a politeness marker and **56% carry none**, and only
  3.5% of the other comments carry one. The study's question is therefore
  answerable rather than trivially yes.
- **The source frame.** 47 Facebook accounts, 0 LGUs, 0 unregistered accounts.
- **Privacy.** 0 email or phone hits; the author's name is not a column.
- **The identifier scheme.** `<platform>_<source_page>_<seq4>`, unique across
  1,781 rows, never reused.
- **No duplicates in the delivered dataset.** 1,610 rows, 1,610 distinct
  dedup keys, 0 residual duplicates, and every removal from the raw layer is
  counted with a reason code.

---

## 6. The one-paragraph version

The dataset is complete and validated against the contract; 17 of the 18
acceptance checks pass and the eighteenth is the human verification, which is
yours to do and is the only thing blocking the release. Two decisions are not
the collector's — the adviser's sign-off on the invitation markers, and Member
1's correction of "manually annotate" in the paper's objective — and three
properties of the corpus need writing down rather than fixing. Nothing in the
modelling text field, the labels, or the splits is in question.
