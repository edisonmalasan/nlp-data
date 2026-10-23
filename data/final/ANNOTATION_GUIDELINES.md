# ANNOTATION_GUIDELINES.md

**Labeling rules for the "actionable suggestion / request" dataset**

| Field | Value |
|---|---|
| Guideline version | `v1.0` |
| Status | **FINAL — applied to the released dataset** |
| Created | 2026-10-20 |
| Owner | Member 4 — **Edison Yin Malasan** (dataset producer, adjudicator) |
| Annotator | `A1` — the annotator engine (`src/annotate/auto_annotator.py`), with LLM adjudication and independent model-assisted verification (see §8.5) |
| Dataset | `data/processed/dataset_v1.csv` |
| Governing contract | `DATA_CONTRACT.md` |
| Task definition source | `docs/NLP-Final-Paper.pdf` §II (Problem Statement) and §II (Scope) |

---

## 1. The task in one sentence

> Decide whether a **public comment** on a Philippine national government agency's social media post **identifies a concrete action the government should take** — i.e. it proposes an action or asks for a specific action or response — and label it `actionable` if it does, `other` if it does not.

You are **not** judging sentiment. You are **not** judging whether you agree with the commenter. You are **not** judging whether the request is feasible, legal, or reasonable. You are **not** judging whether the underlying problem is real.

---

## 2. The core rule (and the one thing you must never do wrong)

### 2.1 The rule

Ask: **"Does this comment point to something specific that the agency could be asked to DO, or that the commenter proposes the agency DO?"**

- **YES → `actionable` (label = 1)**
- **NO → `other` (label = 0)**

### 2.2 The language-neutrality rule — READ THIS BEFORE LABELLING

**Never define the label by surface markers.**

Politeness/request markers — *please*, *dapat*, *sana*, *paki-*, *pakisana*, *can you*, *could you*, *should*, *need to*, *humble request* — are **evidence**, not **the definition**.

> ❌ "A comment with *please* or *dapat* is actionable."
> ✅ "A comment that identifies a concrete action is actionable. *Please* might be in it, or it might not."

**Why this matters (and why it is your problem, not just the modeler's):** the paper's research question asks whether adding these very markers as features improves detection over a plain TF-IDF baseline. If you label by marker, the answer becomes "yes, obviously" and the study proves nothing. The dataset must contain plenty of `actionable` comments **without** any politeness marker, and plenty of `other` comments **with** them. When you notice you are about to label because of a marker, slow down and re-apply §2.1.

Examples of what this means in practice:

| Comment | Marker present? | Correct label | Why |
|---|---|---|---|
| *Please fix the damaged road in our barangay.* | yes | **actionable** | Identifies a concrete action (repair the road). |
| *Hindi naman, kailangan nating ayusin ang kalsada para sa mga mag-aaral.* | no | **actionable** | Identifies an action (fix the road for students) even without a politeness marker. |
| *Sana i-improve na ng DepEd ang sistema ng enrollment.* | yes (*sana*) | **actionable** | Identifies an action (improve the enrollment system). |
| *Please vote for our team.* | yes | **other** | A politeness marker is present, but the comment asks the reader to vote — it does not ask the agency to take an administrative/public-service action. |
| *Salamat sa mga doctor, mabuting trabaho po.* | yes (*mabuting*, *po*) | **other** | Compliment/feedback, no action identified. |

### 2.3 The three questions, in order

Apply them in this order. Stop at the first YES.

1. **Does the comment identify an action, request, or proposal directed at the agency or the government?** → `actionable`.
2. **Does it only describe a problem, state an opinion, complain, thank, react, or ask for information?** → `other`.

Then handle the tie-breakers in §6.

---

## 3. Label definitions

### 3.1 `actionable` (label = 1)

A comment is `actionable` if it does **at least one** of the following:

| Subtype | Description | Surface realization (examples, not criteria) |
|---|---|---|
| **A1 — Request for service/action** | Asks the agency to perform a specific service, fix, repair, provide, release, process, or attend to something. | "Please repair the road", "Kailangan namin ng birth certificate", "Palitan na po ang linya ng number" |
| **A2 — Proposal / recommendation** | Proposes a specific course of action, policy, program, or improvement. | "Dapat magkaroon ng QR code ang payment", "Bakit hindi gawan ng app para sa schedule" |
| **A3 — Conditional / contingent request** | States a need that becomes an action if the agency responds. | "Kung wala pa rin ang tubig, kailangan namin ng alternatibong supply" |
| **A4 — Actionable need with implied target** | Identifies a gap or deficiency whose remedy is obvious from the context of the post. | Reply to "Magkano ang bayad sa ID?" → "Wala pa po ng schedule, kailangan po sana ng bagong slot" |
| **A5 — Multi-action comment** | Proposes several actions. Still **one** label: `actionable`. | "Ayusin ang kalsada at maglagay ng streetlight" |

### 3.2 `other` (label = 0)

A comment is `other` if it is any of the following:

| Subtype | Description | Surface realization (examples, not criteria) |
|---|---|---|
| **O1 — Complaint without proposed action** | Reports or laments a problem but does not say what should be done about it. | "Ang pangit ng kalsada namin" (the paper's own example) |
| **O2 — General wish without identifiable action** | Expresses hope/wish with no specific, actionable object. | "Sana maganda ang buhay natin", "Kaya lang sana" |
| **O3 — Reaction / opinion / political commentary** | Supports, criticizes, praises, mocks, or analyzes; proposes no action. | "HAHAHA legit kayo", "This is the best agency", "Corrupt!" |
| **O4 — Gratitude / praise** | Thanks or compliments. | "Maraming salamat sa tulong ninyo!" |
| **O5 — Question about information** | Asks for a fact, an explanation, or a status, with **no** request for an action to be taken. | "Magkano ang bayarin?" "Kailan po release ang budget?" |
| **O6 — Personal anecdote / story** | Shares an experience without asking for anything. | "Nung bata ako ganito ang kalsada sa amin" |
| **O7 — Chitchat / social / banter** | Jokes, greetings, tag-along replies, emoji, religious/political remarks without any request. | "Amen!", "Good morning po", "HAHAHA" |
| **O8 — Non-actionable information** | Gives information, news, or a link that is not a request. | "Check out this link" |
| **O9 — Meta-discussion about the agency itself** | Praises/criticizes the agency's *performance or reputation* without an actionable ask. | "Galing ng inyo yung service" |

> **Note on O9 vs A1/A2.** "Galing ng inyo yung service" is `other`. "Please improve your service, it's always slow" is `actionable`. The difference is whether an action is identified, not whether the agency is mentioned.

---

## 4. Decision tree

```
Does the comment identify a concrete action, request, or proposal
directed at the agency or government?
│
├─ YES ──────────────────────────────────────────────► ACTIONABLE (1)
│
└─ NO
   │
   ├─ Is it only a complaint/lament without a proposed remedy? ──► OTHER (0)
   ├─ Is it a general wish with no identifiable object? ─────────► OTHER (0)
   ├─ Is it praise, gratitude, reaction, chitchat, banter? ───────► OTHER (0)
   ├─ Is it a question asking only for information/status? ──────► OTHER (0)
   ├─ Is it a political/personal opinion without a request? ────► OTHER (0)
   ├─ Is it purely informational (news, link, anecdote)? ────────► OTHER (0)
   └─ UNSURE ──────────────────────────────────────────────────► flag for adjudication
                                                              (§9) — never guess silently
```

---

## 5. Example bank

The canonical bank. **Adjudicated disagreements are added here** (§10.4). Versioned with the guidelines.

### 5.1 Clear `actionable`

| # | Comment | Language | Label | Rationale |
|---|---|---|---|---|
| 1 | Please repair the damaged road in our barangay. | eng | **1** | Specific action + target. (Paper's example.) |
| 2 | Please po, clean the canal. | mixed | **1** | Specific action requested. (Paper's example.) |
| 3 | Dapat ayusin ang drainage. | fil | **1** | Action (fix drainage) + should. (Paper's example.) |
| 4 | Kailangan po namin ng birth certificate para sa school enrollment. | fil | **1** | Specific service requested. |
| 5 | Hindi naman, kailangan nating ayusin ang kalsada para sa mga mag-aaral. | fil | **1** | Action identified, no politeness marker. |
| 6 | Sana maayos na ang kalsada sa puro. | fil | **1** | Wish attached to an identifiable object (the road) → actionable object. |
| 7 | Paki-release na po ang budget ng school. | fil | **1** | Specific action (release the budget). |
| 8 | I suggest you add a QR code option for payment. | eng | **1** | Concrete proposal. |
| 9 | Bakit walang ganitong option sa app? I suggest adding it. | mixed | **1** | Proposal with a specific change. |
| 10 | Please make the schedule available online, lines are too long. | eng | **1** | Action + rationale. |
| 11 | Kailangan po ng bagong bus route papuntang probinsya. | fil | **1** | Specific service requested. |
| 12 | Please put more barangay health workers in our area. | eng | **1** | Specific staffing action. |
| 13 | Can you please release the list of beneficiaries? | eng | **1** | Requests an action (release), not just information. |
| 14 | Pagkatapos ng bagyo dapat linisin ang mga kanal bago mag-ulan. | fil | **1** | Proposal with a defined object. |
| 15 | Sana magkaroon ng maaaring online appointment para sa DL renewal. | mixed | **1** | Specific service/proposal. |
| 16 | I suggest that the agency publish flood maps in advance. | eng | **1** | Concrete policy proposal. |
| 17 | Pagbigat ng problema, tulong sa pag-ayos ng signal sa amin. | fil | **1** | Implicit request with an identifiable object (signal). |
| 18 | Please clarify and fix the confusing signage at the entrance. | eng | **1** | Two actions, still one comment → 1. |

### 5.2 Clear `other`

| # | Comment | Language | Label | Rationale |
|---|---|---|---|---|
| 19 | Ang pangit ng kalsada namin. | fil | **0** | Complaint without a proposed action. (Paper's example.) |
| 20 | Salamat sa mga doctor, mabuting trabaho po! | mixed | **0** | Gratitude. |
| 21 | Magkano po ang bayarin sa pag-apply ng ID? | mixed | **0** | Information question, no action requested. |
| 22 | HAHAHA legit kayo. | mixed | **0** | Reaction, no request. |
| 23 | Amin is the best agency! God bless you all! | eng | **0** | Praise. |
| 24 | Sana talaga maganda ang buhay natin. | fil | **0** | General wish, no identifiable object. |
| 25 | Nung bata ako ganito pa rin ang kalsada sa amin. | fil | **0** | Anecdote. |
| 26 | Please vote for our team on Sunday. | eng | **0** | Marker present, but no agency action identified. |
| 27 | Kailan po magre-release ang budget ng ahencia? | mixed | **0** | Status/information question. |
| 28 | Corrupt! Bayad kayo ng taxes tapos hindi niyo pinapalitan ang kalsada. | fil | **0** | Criticism without a proposed action. |
| 29 | Check out this link guys. | eng | **0** | Purely informational. |
| 30 | Grabe, sobrang dami nang lumagan na sa espya ngayon. | fil | **0** | Observation. |
| 31 | Kung wala na kayo ng budget, huwag na kumuha ng donations. | fil | **0** | Conditional opinion, no request to the agency for an action on a citizen need. |
| 32 | Amen! God bless po sa inyo lahat. | mixed | **0** | Religious remark, no request. |

### 5.3 Judgment calls (the hard ones)

These are the cases that get disputed. Read them with the adjudicated label and rationale.

| # | Comment | Language | Label | Rationale |
|---|---|---|---|---|
| 33 | *Aba! Tama yan.* (reply to a post about a broken drainage asking citizens to report) | fil | **0** | Agreement with the post; no action requested. |
| 34 | *Same, please fix ours too.* (reply to a complaint post) | eng | **1** | Requests the same action for the commenter's area. |
| 35 | *Sana maayos na ang kalsada.* (no post context) | fil | **1** | An identifiable object (the road) makes the wish actionable. Compare #24 where no object exists. |
| 36 | *Sana maayos lahat.* (no post context) | fil | **0** | No identifiable object → general wish. |
| 37 | *Pakisana pagbutas ng budget para sa libreng gamot.* | fil | **1** | Specific action (release of budget). |
| 38 | *Pagkatapos ng lindol, sana may pangalawang round ng relief.* | fil | **1** | Identifies a needed action (another relief round). |
| 39 | *Ang agency niyo bayad ng tax ng tao para sa isang trapo?* | fil | **0** | Rhetorical criticism, no action proposed. |
| 40 | *Sana hindi na magbayag ng parking sa kalsada...* | mixed | **0** | Wish that a fee be removed — the fee is the object of complaint, but no action is proposed to the agency. *(Edge: annotators often disagree; adjudicated as 0.)* |
| 41 | *I hope the agency prioritizes flood control over new road projects.* | eng | **1** | Specifies a prioritization decision to make. |
| 42 | *Grabe, ang tanaw ng lugar na yan, ang ganda!* | fil | **0** | Compliment about a place. |
| 43 | *Dapat mag-ingat na siya sa social media.* | fil | **0** | Advice directed at a person, not an action for the agency. |
| 44 | *Pagkatapos ng lindol, dapat ayusin na ang daluyan para sa susunod.* | fil | **1** | Identifies an action for the agency. |
| 45 | *Sana maging maayos ang traffic sa EDSA.* | fil | **1** | Identifiable object (traffic) → actionable. |

> **Important:** #35 vs #36 is the single most common dispute. The discriminator is **whether an identifiable object of action exists**. If you can point to *what* should be done or changed, it is `actionable`. If the wish is only about a general state of the world, it is `other`.

### 5.4 Code-switching cases

| # | Comment | Language | Label | Rationale |
|---|---|---|---|---|
| 46 | *Please fix the damage road, ang pangit na!* | mixed | **1** | Action requested; the complaint clause doesn't change the label. |
| 47 | *Grabe naman, bakit ganyan? So unfair!* | mixed | **0** | Reaction to a decision; no action proposed. |
| 48 | *Sana maayos ang signal sa amin, please improve the tower.* | mixed | **1** | Two actions (fix signal, improve tower) → still one comment, label 1. |
| 49 | *Ito ba ang sagot sa complaint namin?* | mixed | **0** | Sarcastic rhetorical question, no action. |
| 50 | *Salamat, maging maayos ang inyong serbisyo.* | mixed | **0** | Gratitude + general wish, no identifiable action object. |

---

## 6. Edge cases and tie-breakers

Apply in order; the first matching rule wins.

### 6.1 Questions vs. requests

A question is `actionable` **only if** answering it requires the agency to **do something**, not to **tell something**.

| Question | Label | Why |
|---|---|---|
| *Magkano po ang bayarin sa ID?* | **0** | Information only. |
| *Kailan po magre-release ng budget?* | **0** | Status only. |
| *Bakit hindi pa naaayos ang kalsada?* | **0** | Explanation sought. |
| *Puwede bang pa-appointment online?* | **1** | Answering requires the agency to *provide an online appointment*. |
| *Puwede bang mag-issue ng replacement certificate?* | **1** | Requires the agency to *issue*. |

### 6.2 Complaints

- Complaint **with** a proposed remedy → `actionable`.
- Complaint **without** a proposed remedy → `other`.
- The presence of harsh language never changes the label.

### 6.3 Wishes and hopes

- Wish with an **identifiable object of action** → `actionable` (e.g., *Sana maayos ang kalsada*, *Sana maging maayos ang signal*).
- Wish with **no identifiable object** → `other` (e.g., *Sana maganda ang buhay natin*, *Sana masaya kayo*).

### 6.4 Sarcasm and irony

Label the **literal propositional content** of the comment, not its tone. If the literal content contains a request, it is `actionable`.

- *Legal naman pala yang kalsada, baka nga kayo ang may kasalanan.* → **0** (literal content is an accusation, no request).
- *Sana talaga maayos na, kasi kapag maliit na lang kami.* → **0** (literal content: a general wish about roads with an identifiable object — hmm, this one gets flagged).

> **Flagging rule:** if a comment's tone is ambiguous and two annotators would reasonably differ, mark it `FLAG` in the tool's notes field rather than guessing. Flags are adjudicated centrally (§9). Do **not** resolve it alone, and do **not** leave it unlabeled.

### 6.5 Conditional requests

*Kung wala pa rin ng tubig, kailangan namin ng alternatibong supply* → **actionable** (the condition plus the need point to a concrete remedy).

### 6.6 Advice directed at a person vs. the agency

- Directed at the agency or the government → judge under §2.1.
- Directed at an individual (an official, a commenter, the public) → `other` (*Dapat mag-ingat na siya sa social media*).

### 6.7 Replies and post context

**Always read the post before labeling.** The post text is displayed in the labeling tool. Use it to resolve the referent, but **label the comment itself**, not the post. The corpus is top-level comments only; there is no parent comment.

- If the comment refers to something in the post (e.g. *"Yung nasa post na 'schedule' ay dapat i-extend"*), the post context supplies the referent. The comment still needs to identify an action.
- If the comment is pure reaction to the post (e.g. *"Aba! Tama yan."*) → `other`.
- If the comment asks for information about the post (e.g., *"Magkano po ng fee na sinabi?"*) → `other`.

### 6.8 Mentions, links, hashtags

- A hashtag naming an issue without a request (*#FloodControl*) → `other`.
- A comment whose entire content is a URL → excluded at cleaning (`X_EMPTY`), not labeled.

### 6.9 Threats, abuse, and insults

- Abuse or insults without a request → `other`.
- A threat that also names an action the agency should take (rare) → judge under §2.1.

### 6.10 Religious, political, and sensitive content

Never adjust your label because of the topic. Judge the text only. Sensitive content is labeled like everything else and handled under the anonymization rules in `DATA_CONTRACT.md` §11.

### 6.11 Multilingual / non-target languages

Comments not in Filipino, English, or a mix are **excluded before labeling** (`X_LANG`). If you encounter one in the tool, mark it `X_LANG` in the notes field and move on — do not assign a label.

### 6.12 Mixed-language comments with non-target languages

A comment that is mostly Filipino/English with a small amount of another language stays in the dataset and is labeled normally.

---

## 7. Language tagging

Alongside the label, set `language`:

| Value | Meaning |
|---|---|
| `fil` | Predominantly Filipino / Tagalog. |
| `eng` | Predominantly English. |
| `mixed` | Both meaningfully present — **the study's core population.** |

Guidance:
- Tag the **predominant** language.
- A single English clause inside an otherwise Filipino comment is usually `fil`, unless the English carries the action and the Filipino is incidental ("Ang kalsada namin please fix" → `mixed`).
- Code-switching often shows as Filipino/English word pairs in one phrase ("dapat i-fix", "paki-install ng app") → that is `mixed`.
- When torn between `fil` and `mixed`, prefer `mixed`. Under-tagging `mixed` biases the study's headline population.

---

## 8. Workflow

### 8.1 Roles

The dataset is labeled by an **automated annotator** (`src/annotate/auto_annotator.py`)
following this document, with LLM adjudication and **independent model-assisted verification**.

| Role | Who | Scope |
|---|---|---|
| Annotator engine | `src/annotate/auto_annotator.py` — heuristic scoring | 100% of the dataset |
| Adjudicator | An LLM working from this document's decision tree, resolving every row below 0.85 confidence plus a 10% audit sample | 100% of flagged cases |
| Independent verifier | A separate model annotator, reviewing rows **without seeing the engine's label first** (recorded as `llm_verified`) | ≥ 100 random rows |

The engine is **not** the rule. This document is the rule. The engine triages: it settles
the obvious cases and hands everything it is not sure about to an adjudicator who reads the
comment and applies §2 and §4.

Because one annotator produces the labels, the reliability measurement is **intra-annotator
reliability** (test-retest) — a blinded re-label pass by the same annotator — and not
inter-annotator agreement (§10.1).

### 8.2 Pass structure

1. **Guideline calibration (before production).** Label a **30-row pilot batch**. For each
   pilot row, write down *why* it got the label in the note field, then compare against the
   example bank in §5. If your reasoning contradicts the bank, the guideline is wrong — amend
   it and bump `guideline_version` before you go further.
2. **Production pass.** Label **100%** of the pool. Work in batches of 50–100 with breaks
   (§8.4). Set `label`, `label_str`, and `language`.
3. **Washout.** Leave the data alone for **at least 7 days**. Do not look at the labels during
   this time. The washout is what makes the next pass a real measurement rather than a memory
   test — without it, κ would be inflated by recall.
4. **Blinded re-label pass.** Re-label a random **20% subset (≥ 200 rows)**, stratified by
   class and source page, **without** seeing your first-pass labels. The labeling tool must
   hide the `label` column for this pass. Store the second reading in `label_2`.
5. **Reliability check.** Compute Cohen's κ between `label` and `label_2`. Gate:
   **κ ≥ 0.60** (§10.1). If it fails, go to step 6.
6. **Resolve and re-check.** Read every disagreement, decide the correct label against the
   guidelines, and record it in `adjudicated_by` and `adjudication_note` with the rule that
   decided it. **Do not simply take the first-pass label.** Add each case to the example bank
   (§10.4). If the disagreements reveal that the *guidelines* were unclear rather than that
   you misapplied them, amend the guidelines, bump `guideline_version`, and re-label the
   affected rows — labels from different guideline versions are never mixed in one release.
7. **Finalization.** `label` holds the final answer for every row, `label_2` holds the second
   reading, and `agreement` records whether the two passes matched.

### 8.3 Tool requirements

The labeling tool must:

- Display **post text**, **post date**, and **source agency** next to the comment. (§8.2 requirement, non-negotiable.) The corpus is top-level comments only, so no parent comment is shown.
- Allow setting `label` and `language` and a free-text note.
- **Hide** `label_2`, `agreement`, `adjudicated_by`, and `label` itself during the blinded
  re-label pass (step 4 of §8.2). A pass where you can see your own earlier answer is
  not a reliability measurement.
- Allow marking a row `FLAG` for a second look during the reliability pass.
- Export to CSV with the exact column names in `DATA_CONTRACT.md` §5.2.

Recommended: Doccano or Label Studio (both open source, both support multi-annotator assignment and context display). A simple local HTML/CSV viewer is acceptable if it satisfies the above.

### 8.4 Labeling rules of conduct

- Label from the **comment + post context**, nothing else (no comments on the agency's other posts, no outside knowledge of the issue).
- Do **not** skip a row. Use `FLAG` for anything unclear.
- Work in batches of **50–100 rows**, then take a break. Fatigue is the main source of drift.
- Do **not** consult the write-up, the paper, or your own earlier notes while labeling — only the comment and its context.
- Log any suspected platform artifact or spam pattern in the note field rather than deleting the row yourself.


### 8.5 The automated annotation workflow

This is the default path. It exists so the dataset does not depend on one person typing a
label for every comment, while keeping every label traceable to this document.

#### The three stages

**Stage 1 — Cue extraction.** `src/annotate/auto_annotator.py` extracts signals from
each comment: request markers, action verbs, strong request frames (`dapat`, `kailangan`,
`need to`), action objects, complaint markers, gratitude, reaction, information questions,
and refusals.

**Stage 2 — Heuristic scoring.** Cues become a suggested label, a confidence, and the
rule that fired.

| Rule | Label | Confidence | Auto-decided? |
|---|---|---|---|
| `request_marker + action_verb` | actionable | 0.85–0.90 | yes |
| `strong_frame + action_object` | actionable | 0.88 | yes |
| `strong_frame_only` | actionable | 0.80 | no |
| `request_marker + object_only` | actionable | 0.60 | **no — adjudicated** |
| `action_verb_only` | actionable | 0.78 | no |
| `gratitude_or_reaction` | other | 0.90 | yes |
| `complaint_without_remedy` | other | 0.88 | yes |
| `information_question` | other | 0.85 | yes |
| `needs_adjudication` | — | 0.00 | **no — adjudicated** |

**Rows below 0.85 confidence are never auto-decided.** They go to adjudication.

**Stage 3 — Adjudication.** Two groups of rows are exported for a person (or an agent)
to read and decide:

1. Every row the heuristic could not decide.
2. A **random 10% audit sample** of the rows it *could* decide, fixed seed `42`.

The audit sample is what makes the heuristic's accuracy a measurement rather than an
assumption. Every exported row carries the comment, the post context, the heuristic's
suggestion, and the evidence behind it — so the adjudicator sees everything §8.4 requires
and nothing that would bias the decision. The corpus is top-level comments only, so there
is no parent comment.

#### Running it

```bash
python src/annotate/auto_annotator.py score \
    --pool       data/processed/candidate_pool.csv \
    --out        data/interim/auto_scored.csv \
    --review-out data/interim/review_batches/

# work the batches, write data/interim/agent_decisions.csv, then:
python src/annotate/auto_annotator.py apply \
    --scored    data/interim/auto_scored.csv \
    --decisions data/interim/agent_decisions.csv \
    --out       data/processed/dataset_v1.csv
```

Full procedure in `src/annotate/README.md`.

#### What the adjudicator must do

- Read the **comment and its post context**. Never from the comment alone (§8.4).
- Apply §2 and §4. The heuristic's suggestion is a hypothesis, not an answer.
- **Do not anchor.** For an `audit` row, decide first, then compare. Overriding the
  heuristic is a legitimate outcome and is recorded as such.
- Record a **one-line note** naming the rule that decided it (`§6.3 — identifiable
  object of action`). This is what makes the label auditable.
- Set `verification` on the row: `auto` for engine-only labels, `llm_verified` for rows an
  independent model annotator checked blind, `human_verified` for rows a person checked,
  `human_labeled` for rows a person labelled from scratch.

#### Independent verification (required before release)

- [ ] Verify **≥ 100 random rows** that the engine labeled, **without seeing the
      engine's label first**.
- [ ] Record the agreement rate and Cohen's κ between the second reading and the engine's.
- [ ] Set `verification` on those rows to the method actually used (`llm_verified` or
      `human_verified`). Never record a model pass as human.
- [ ] Report both numbers in the write-up.

The released dataset used **model-assisted verification**: 120 rows, 93.3% agreement,
κ = 0.79. The 332-row blinded re-label reached 92.5% agreement and κ = 0.72. Twenty-four
pass-1 labels were corrected during adjudication against the blind pass; the corrections
are in `data/provenance/adjudication_log.csv` and are excluded from the κ.

#### Rules the engine must never break

1. **A politeness marker alone never makes a row actionable** (§2.2). The engine encodes
   this by never scoring on markers by themselves — a marker counts only alongside an
   action verb, a strong request frame, or an action object.
2. **The most disputed class is never auto-decided.** `request_marker + object_only`
   (*"Sana maayos ang kalsada"*) always routes to adjudication, because §5.3 #35 vs #36
   is the most common dispute in this document.
3. **Every row ends up with a decision.** Any row still below threshold at merge time is
   reported as a warning and blocks release.
4. **The heuristic is triage, not the rule.** If the engine and this document disagree, the
   document wins — fix the engine.

#### How to describe this in the write-up

This is **LLM-assisted annotation with independent verification**. Say so, and state:

- the engine and its version,
- the share of rows auto-decided vs adjudicated vs verified,
- the verification sample size, agreement rate, κ, and the method actually used,
- the blinded re-label κ and whether a washout was observed.

If the verification pass was performed by a model, call it **model-assisted
verification**. Do **not** describe it as human verification, and do **not** describe
automated labeling as manual annotation. Either is a misreport, and it is the one thing
in this section that is not negotiable.

---

## 9. Resolving disagreements between your two passes

When your first pass and your blinded re-label pass disagree:

1. Re-read the comment and the post context, without looking at either label.
2. Apply the rules in this document and decide which label is correct.
3. Record: the final `label`, `adjudicated_by` (your annotator ID), and a **one-line
   `adjudication_note`** stating the rule that decided it (e.g., "§6.3 — identifiable
   object present").
4. Add the case to the **example bank** (§10.4) with its rationale.
5. If the disagreement reveals that the **guidelines themselves are unclear** rather than that
   you misapplied them, amend the guidelines and bump `guideline_version`. Under a bumped
   version, previously labeled rows in the affected area are **re-annotated**.

**Do not resolve a disagreement by keeping whichever label you wrote first.** That defeats the
purpose of the second pass. Resolve it by the rule, not by the order of writing.

**Disagreement is not failure.** A κ of 0.70–0.80 on hard cases like "is this wish
actionable?" is a good, honest result. Report it as it is.

---

## 10. Quality control

### 10.1 Reliability

This dataset is labeled by one annotator, so there is no inter-annotator agreement to report.
The reliability statistic is **intra-annotator reliability**, measured by Cohen's kappa between
the first pass and the **blinded re-label pass** (§8.2, step 4).

| Item | Value |
|---|---|
| Metric | **Cohen's kappa** between `label` (pass 1) and `label_2` (blinded re-label) |
| Subset | Random 20% of the primary corpus (**332 of 1,657 rows**) |
| Washout | **0 days** (the two passes ran in the same session) — κ is therefore an **upper bound**, not a true test-retest estimate |
| Interpretation (Landis & Koch 1977) | `< 0.20` slight · `0.21–0.40` fair · `0.41–0.60` moderate · `0.61–0.80` substantial · `0.81–1.00` almost perfect |
| **Gate** | **κ ≥ 0.60** — below this, resolve the disagreements and re-measure |
| Result | **κ = 0.72** (92.5% agreement); 25 rows disagreed and 24 were corrected during adjudication |
| Report | κ, the disagreement breakdown (which error dominates — most commonly O1↔A1, "complaint with vs. without remedy"), and the count of resolved rows |
| Also report | Independent verification of 120 rows: 93.3% agreement, **κ = 0.79**, method `llm_verified` (model-assisted, not human) |

**How to describe it in the write-up.** Call it *intra-rater reliability* or *intra-annotator
agreement* from a blinded re-annotation pass. **Do not call it inter-annotator agreement** —
there is only one annotator, and claiming otherwise is a misreport. Because the re-label ran
without a washout, report κ as an upper bound and say so.

### 10.2 Common error patterns to watch for

| Pattern | Symptom | Fix |
|---|---|---|
| **Marker bias** | Labeling `actionable` because the comment contains *please*/*dapat* | Re-read §2.2. Cross-check the `actionable` set for a sample of marker-free comments. |
| **Sentiment drift** | Treating "ang galit ng tao, ang lupit" as actionable because the tone is urgent | Re-read §2.1: tone is never the label. |
| **Wish/object confusion** | Labeling every *sana* sentence as actionable | Apply §6.3 — is there an identifiable object of action? |
| **Over-labeling** | `actionable` rate climbing far above the natural prior in the collection | Check the class distribution; recompute κ on a fresh double-annotated batch. |
| **Question confusion** | Labeling all questions as actionable | Apply §6.1. |
| **Context neglect** | Labeling replies without reading the post | Apply §6.7. |

### 10.3 In-run monitoring

Every ~200 rows, the adjudicator reviews:
- the running class distribution,
- a random 20-row sample of your own labels, re-checked against the guidelines blind,
- all FLAGs,
- every row where the two passes disagreed.

### 10.4 Example bank maintenance

Adjudicated cases are appended to §5 with: comment text, language, final label, the rule that decided it, and the guideline version in force. The bank is the paper's Appendix material and the fastest way to train new annotators.

### 10.5 Auto-annotation assistant (if used)

An automated assistant may pre-label rows to speed up triage, but **only** after it passes the gate defined in `DATA_CONTRACT.md` §10.7 (macro-F1 ≥ 0.80 **and** κ ≥ 0.60 on an independently verified gold set).

**Annotator obligations when pre-labeled rows are shown:**

- **Every pre-labeled row must be individually confirmed or corrected.** Do not accept a batch uncritically. Assisting means *checking*, not *approving*.
- **Do not anchor on the draft label.** Read the comment and decide first; the assistant's guess is a hypothesis, not an answer.
- **Keep your pass-1 labels away from the assistant's drafts.** Label the pool yourself first; use the assistant only for rows you have not yet reached.
- **Report the assistant's wrong suggestions.** If you change a draft label, note why — these corrections are the most valuable signal about where the assistant fails, and the class distribution of corrections gets reported in the paper.

The released dataset used this path: the engine scored every row, adjudication resolved every
row below 0.85, and 24 labels were corrected against an independent blind pass. The
verification method is recorded as `llm_verified`, not `human_verified`.

### 10.6 Guideline version history

| Version | Date | Author | Change |
|---|---|---|---|
| `v1.0-draft` | 2026-10-20 | M4 (MALASAN) | Two-label taxonomy from the paper's Scope; core action-based rule; language-neutrality rule; decision tree; 50-example bank; edge-case tie-breakers; workflow and QC. |
| `v1.0-draft` (annot. engine) | 2026-10-20 | M4 (MALASAN) | Added §8.5, the automated annotation workflow: cue extraction, heuristic scoring with confidence thresholds, adjudication of every low-confidence row plus a 10% audit sample, and independent verification of ≥ 100 rows. |
| `v1.0` | 2026-10-23 | M4 (MALASAN) | **Released.** Applied to all 1,657 primary rows. Verification recorded as `llm_verified` (model-assisted, 120 rows, κ = 0.79); blinded re-label 332 rows, κ = 0.72 with no washout (upper bound); 24 labels corrected against the blind pass. Top-level comments only. |

> **Every label in the dataset carries the `guideline_version` it was produced under** (`DATA_CONTRACT.md` §5.2, column 29). Labels from different guideline versions are never mixed in one release.

---

## 11. Quick checklist before you submit a row

- [ ] I read the **post context** (post text, date, agency). The corpus is top-level comments only; there is no parent comment.
- [ ] I decided based on **whether an action is identified** — not on sentiment, tone, markers, or length.
- [ ] If I found a marker, I checked the action anyway.
- [ ] If it is a question, I checked whether the answer requires an **action** or only **information**.
- [ ] If it is a wish, I checked for an **identifiable object of action**.
- [ ] I set `language` (`fil` / `eng` / `mixed`), preferring `mixed` when torn.
- [ ] I did **not** use the label column to mean anything other than 0/1 as defined.
- [ ] Anything genuinely ambiguous → `FLAG` + note, not a guess.

---

## 12. Glossary

| Term | Meaning in this project |
|---|---|
| **Actionable** | Label 1 — the comment identifies a concrete action for the agency. |
| **Other** | Label 0 — the comment does not. |
| **Action object** | The thing that should be changed, fixed, provided, or done. Its presence distinguishes an actionable wish from a general one. |
| **Marker** | A surface request/politeness word (*please, dapat, sana, paki-*). Evidence, never the definition. |
| **Post context** | The source post's text, date, and agency. The corpus is top-level comments only, so no parent comment is shown. |
| **Flag** | A row an annotator could not confidently label; routed to the adjudicator. |
| **Blinded re-label pass** | The same annotator re-labeling a subset after a washout, without seeing the first pass. The basis of the κ figure. |
| **Resolution** | Deciding a pass-1 vs pass-2 disagreement against the guidelines, with a written rule reference. |
| **Gold set** | 120 self-labeled rows used to evaluate the auto-annotator and to check κ before production labeling. |
| **Prior** | The natural fraction of `actionable` comments in collected data, before any balancing. |
| **Mixed / code-switched** | A comment containing both Filipino and English in meaningful proportion. |
