# ANNOTATION_GUIDELINES.md

**Labeling rules for the "actionable suggestion / request" dataset**

| Field | Value |
|---|---|
| Guideline version | `v1.0-draft` |
| Status | **DRAFT — must be agreed by the annotation team before labeling starts** |
| Created | 2026-10-20 |
| Owner | Member 4 — **Edison Yin Malasan** (dataset producer, adjudicator) |
| Annotators | A1–A6 (pseudonymous IDs; names never stored in the dataset) |
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

**Why this matters (and why it is your problem, not just Member 5's):** the paper's research question asks whether adding these very markers as features improves detection over a plain TF-IDF baseline. If you label by marker, the answer becomes "yes, obviously" and the study proves nothing. The dataset must contain plenty of `actionable` comments **without** any politeness marker, and plenty of `other` comments **with** them. When you notice you are about to label because of a marker, slow down and re-apply §2.1.

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

**Always read the post before labeling.** The post text and, for replies, the parent comment are displayed in the labeling tool. Use them to resolve the referent, but **label the comment itself**, not the thread.

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

| Role | Responsibility |
|---|---|
| Annotator A1–A6 | Labels assigned rows. Sees post context. Does not see other annotators' labels. |
| Second annotator | Labels the **20% overlap subset** (≥ 200 rows), stratified by class and source page. |
| Adjudicator (M4) | Resolves all disagreements; escalates guideline-level disputes to the adviser. |

### 8.2 Pass structure

1. **Guideline agreement (before production).** All annotators independently label the same **30-row pilot batch**. Discuss disagreements. Amend the guidelines if needed → `guideline_version` bump.
2. **Gold set (120 rows).** Two annotators independently label the same 120 rows; adjudicate; compute Cohen's κ. Gate: **κ ≥ 0.60** to proceed to production labeling (§10.5).
3. **Production.** Each row is labeled by at least one annotator; 20% by two.
4. **Adjudication.** Every disagreement goes to the adjudicator within 48 hours.
5. **Finalization.** Disagreements resolved → `label` set, `label_2` retained, `agreement` and `adjudicated_by` filled.

### 8.3 Tool requirements

The labeling tool must:

- Display **post text**, **post date**, **source agency**, and **parent comment text** (for replies) next to the comment. (§8.2 requirement, non-negotiable.)
- Allow setting `label` and `language` and a free-text note.
- **Hide** `label_2`, `agreement`, `adjudicated_by`, and any other annotator's output from the annotator.
- Allow marking a row `FLAG` for adjudication.
- Export to CSV with the exact column names in `DATA_CONTRACT.md` §5.2.

Recommended: Doccano or Label Studio (both open source, both support multi-annotator assignment and context display). A simple local HTML/CSV viewer is acceptable if it satisfies the above.

### 8.4 Labeling rules of conduct

- Label **independently**. Do not consult other annotators' decisions before submitting your own.
- Label from the **comment + post context**, nothing else (no comments on the agency's other posts, no outside knowledge of the issue).
- Do **not** relabel a row after seeing the adjudicator's decision. If you still disagree, say so in the note field.
- Do **not** skip a row. Use `FLAG` for anything unclear.
- Work in batches of **50–100 rows**, then take a break. Fatigue is the main source of drift.
- Log any suspected platform artifact or spam pattern to the adjudicator rather than deleting it yourself.

---

## 9. Adjudication

When two annotators disagree:

1. The adjudicator reads the comment, the post context, both labels, and the annotators' optional notes.
2. The adjudicator applies the rules in this document and picks the label.
3. The adjudicator records: final `label`, `adjudicated_by`, and a **one-line `adjudication_note`** stating the rule that decided it (e.g., "§6.3 — identifiable object present").
4. The case is **added to the example bank** (§10.4) with its rationale.
5. If the dispute reveals that the **guidelines themselves are unclear** (not just that the annotator misapplied them), the guidelines are amended and `guideline_version` is bumped. Under a bumped version, previously labeled rows in the affected area are **re-annotated**.

**Adjudication is not a popularity vote.** Two annotators agreeing on a rule misreading does not make it right.

---

## 10. Quality control

### 10.1 Inter-annotator agreement

- Metric: **Cohen's kappa** on the double-annotated subset.
- Interpretation (Landis & Koch 1977): `< 0.20` slight · `0.21–0.40` fair · `0.41–0.60` moderate · `0.61–0.80` substantial · `0.81–1.00` almost perfect.
- **Gate: κ ≥ 0.60** to start/continue production labeling.
- Report: κ, the disagreement breakdown (which subtype of error dominates — most commonly O1↔A1, i.e. "complaint with vs. without remedy"), and the count of adjudicated rows.

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
- a random 20-row sample of labels from each annotator,
- all FLAGs,
- the rows with the largest token-level difference between the annotators' labels (if the tool supports it).

### 10.4 Example bank maintenance

Adjudicated cases are appended to §5 with: comment text, language, final label, the rule that decided it, and the guideline version in force. The bank is the paper's Appendix material and the fastest way to train new annotators.

### 10.5 Auto-annotation assistant (if used)

An automated assistant may pre-label rows to speed up triage, but **only** after it passes the gate defined in `DATA_CONTRACT.md` §10.7 (macro-F1 ≥ 0.80 **and** κ ≥ 0.60 on a 120-row human-adjudicated gold set).

**Annotator obligations when pre-labeled rows are shown:**

- **Every pre-labeled row must be individually confirmed or corrected.** Do not accept a batch uncritically. Assisting means *checking*, not *approving*.
- **Do not anchor on the draft label.** Read the comment and decide first; the assistant's guess is a hypothesis, not an answer.
- **Report the assistant's wrong suggestions.** If you change a draft label, note why — these corrections are the most valuable signal about where the assistant fails, and the class distribution of corrections gets reported in the paper.

### 10.6 Guideline version history

| Version | Date | Author | Change |
|---|---|---|---|
| `v1.0-draft` | 2026-10-20 | M4 (MALASAN) | Initial guidelines. Two-label taxonomy from the paper's Scope; core action-based rule; language-neutrality rule; decision tree; 50-example bank; edge-case tie-breakers; workflow and QC. |

> **Every label in the dataset carries the `guideline_version` it was produced under** (`DATA_CONTRACT.md` §5.2, column 29). Labels from different guideline versions are never mixed in one release.

---

## 11. Quick checklist before you submit a row

- [ ] I read the **post context** (post text, date, agency, parent comment if it is a reply).
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
| **Post context** | The source post's text and metadata, plus the parent comment for replies. Shown to every annotator. |
| **Flag** | A row an annotator could not confidently label; routed to the adjudicator. |
| **Double annotation** | Two annotators labeling the same row independently, blind to each other. |
| **Adjudication** | The adjudicator's resolution of a disagreement, with a written rule reference. |
| **Gold set** | 120 human-labeled, adjudicated rows used to evaluate the auto-annotator and to compute a pre-production κ. |
| **Prior** | The natural fraction of `actionable` comments in collected data, before any balancing. |
| **Mixed / code-switched** | A comment containing both Filipino and English in meaningful proportion. |
