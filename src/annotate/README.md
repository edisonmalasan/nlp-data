# `src/annotate/` — automated annotation

This folder runs the labeling stage. It exists so the dataset does not depend on one
person typing labels for a thousand comments.

## The shape of it

```
candidate_pool.csv
        │
        │  score
        ▼
auto_scored.csv ──────────────────────────────┐
        │                                      │
        │  every row below threshold,           │  confident rows, kept as-is
        │  plus a 10% random audit sample       │
        ▼                                      │
review_batches/batch_001.jsonl ...            │
        │                                      │
        │  adjudicate (agent or human)          │
        ▼                                      ▼
agent_decisions.csv ────────────────► dataset_v1.csv
```

**The heuristic is triage, not the annotation rule.** It decides the obvious cases
(gratitude, pure reaction, complaint with no remedy, clear request + action verb) and
routes everything ambiguous to adjudication. The binding rules stay in
`docs/ANNOTATION_GUIDELINES.md`.

## Running it

### 1. Score the pool

```bash
python src/annotate/auto_annotator.py score \
    --pool      data/processed/candidate_pool.csv \
    --out       data/interim/auto_scored.csv \
    --review-out data/interim/review_batches/ \
    --batch-size 50
```

Prints how many rows were confident vs. how many need adjudication, and writes the
review batches plus a `_manifest.json`.

### 2. Adjudicate the review batches

Each line of `batch_NNN.jsonl` carries everything needed to apply the guideline:

```json
{
  "comment_id": "fb_dost_pagasa_0007",
  "comment_text": "Sana maayos ang kalsada.",
  "post_text": "PAGASA: ... advisory ...",
  "heuristic_label": 1,
  "heuristic_confidence": 0.6,
  "heuristic_rule": "request_marker + object_only",
  "heuristic_evidence": "sana; kalsada",
  "review_kind": "uncertain"
}
```

Work the batch by applying the decision tree in `docs/ANNOTATION_GUIDELINES.md` §4 to
each row, and write the result to `data/interim/agent_decisions.csv` — one JSON object
per line:

```json
{"comment_id": "fb_dost_pagasa_0007", "label": 1, "language": "fil",
 "note": "§6.3 - identifiable object of action (the road)", "verification": "auto"}
```

`review_kind` tells you what you are doing:

| `review_kind` | What it means | What to do |
|---|---|---|
| `uncertain` | The heuristic could not decide this one | Label it yourself from the comment + post context |
| `audit` | The heuristic was confident | **Check it.** Confirm or overturn. These are the rows that tell you whether the heuristic is trustworthy |

An agent (Claude, GPT, any capable model) can run the adjudication. So can you. The
guidelines are written to be readable by either.

### 3. Merge the decisions back

```bash
python src/annotate/auto_annotator.py apply \
    --scored    data/interim/auto_scored.csv \
    --decisions data/interim/agent_decisions.csv \
    --out       data/processed/dataset_v1.csv
```

Rows with no decision keep their heuristic label and are reported as a warning. **Every
row must have a decision before release.**

### 4. Independent verification (required before release)

Verify a **random sample of ≥ 100 rows** that the assistant labelled, without seeing the
assistant's label first. The verifier may be a person or a separate model annotator; record
which one was used. Report:

- how many rows were verified,
- the agreement rate,
- Cohen's κ between the second reading and the assistant's label,
- the method actually used.

Set `verification` on those rows to `llm_verified` or `human_verified` — never record a model
pass as human. The released dataset used `llm_verified`: 120 rows, 93.3% agreement, κ = 0.79.

### 5. Blinded re-label pass (reliability)

See `docs/ANNOTATION_GUIDELINES.md` §8.3. Re-label the same 20% sample **blind** (the `label`
column must be hidden) and compute Cohen's κ between `label` and `label_2`. Gate: **κ ≥ 0.60**.
A washout of ≥ 7 days is preferred; if the pass runs without one, report κ as an upper bound.
The released dataset re-labelled 332 rows with no washout: κ = 0.72 (upper bound).

## Files

| File | Role |
|---|---|
| `auto_annotator.py` | Cue extraction, heuristic scoring, batch export, decision merge |
| `README.md` | This file |

## Tuning the cue lists

The cue lists at the top of `auto_annotator.py` are the only thing that needs tuning
against your corpus. They are deliberately **recall-oriented** — a cue that fires wrongly
costs a row of adjudication, but a cue that never fires means a request gets silently
missed, which is worse.

Two rules when editing them:

1. **Never add a politeness marker to `ACTION_VERBS`.** Markers are evidence, not
   definitions (`docs/ANNOTATION_GUIDELINES.md` §2.2). `maayos ang` was removed from that
   list for exactly this reason — "the road is fixed" is a state, not an action.
2. **Keep `STRONG_REQUEST_FRAMES` small and frame-like.** `dapat`, `kailangan`,
   `need to` imply an action on their own; `sana` does not. `sana` stays in
   `REQUEST_MARKERS`, where it only counts when paired with an actual action verb.

After editing, re-run the checks in `docs/ANNOTATION_GUIDELINES.md` §5 against the
scorer and confirm the disputed examples in §5.3 still route to adjudication rather than
being auto-decided.
