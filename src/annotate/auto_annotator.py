"""
auto_annotator.py — deterministic pre-labeling for the actionable-suggestion dataset.

Purpose
--------
Turn a cleaned candidate pool into labelled rows, without hand-labeling every comment.

Architecture (three stages, deliberately separated so nothing is decided by a
keyword alone):

  Stage 1  CUE EXTRACTION      extract signals from the comment text
  Stage 2  HEURISTIC SCORE     turn signals into a suggested label + confidence + evidence
  Stage 3  REVIEW EXPORT       anything not confident enough is exported for agent
                                adjudication, along with a random audit sample of the
                                confident rows

The heuristics in Stage 2 are NOT the annotation rules. They are a triage device.
The binding rules live in docs/ANNOTATION_GUIDELINES.md, and every row that the
guidelines would treat ambiguously is routed to Stage 3 rather than guessed.

Two hard rules this file must never break:

  1. A politeness marker is EVIDENCE, never the definition. (GUIDELINES 2.2)
     A comment containing "please" is only actionable if an action is identified.
  2. Every excluded/uncertain row leaves a trail. Nothing is dropped silently.

Usage
-----
    # score the pool and export what needs adjudication
    python src/annotate/auto_annotator.py score \
        --pool data/processed/candidate_pool.csv \
        --out  data/interim/auto_scored.csv \
        --review-out data/interim/review_batches/

    # merge adjudicated decisions back in
    python src/annotate/auto_annotator.py apply \
        --scored data/interim/auto_scored.csv \
        --decisions data/interim/agent_decisions.csv \
        --out  data/processed/dataset_v1.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re
import sys
import unicodedata
from dataclasses import dataclass, field, asdict
from typing import Iterable

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LABEL_ACTIONABLE = 1
LABEL_OTHER = 0

# Rows scoring below this go to agent adjudication.
CONFIDENCE_THRESHOLD = 0.85

# Fraction of confident rows pulled in as a random audit sample.
AUDIT_SAMPLE_RATE = 0.10

# Fixed so the audit sample is reproducible.
RANDOM_SEED = 42

# --- Filipino / English request markers (EVIDENCE, not the definition) --------
REQUEST_MARKERS = [
    # English
    "please", "pls", "kindly", "i suggest", "suggestion", "suggest that",
    "i propose", "proposal", "i recommend", "recommendation", "we request",
    "requesting", "would like to", "could you", "can you", "would you",
    "need to", "should be", "ought to", "i urge", "we urge", "pleaseeee",
    # Filipino
    "paki-", "pakisana", "pakiusap", "dapat", "dapat ayusin", "kailangan",
    "gusto kong", "gustong", "nais kong", "nais ko", "hangga\'t", "huwag",
    "sana", " sana ", "ipagbigay", "ipagkaloob", "ipataas", "ipaliwanag",
    "ipinapayong", "hinihingi ko", "humingi", "sumusulat ako", "ang pakikipag-ugnayan",
]

# --- action verbs: something the agency could DO ----------------------------
ACTION_VERBS = [
    # Filipino
    "ayusin", "ayusin ang", "ayusin yung", "linisin", "linisin ang", "palitan",
    "palitan ang", "ibigay", "ipagbigay", "gawan", "gawan ng", "magtayo", "magtatayo",
    "ipaayos", "ipataguyod", "mag-issue", "ipinalit", "ibinigay", "ipaglabag",
    "mag-install", "i-install", "paunawaan", "ipaalam", "ipaabot", "paganlarin",
    "bayaran", "ipagbayad", "magbukas", "bukasan", "isama", "isama sa", "idagdag",
    "dagdagan", "alisin", "tanggalin", "ilipat", "ipatayo", "maitatayo", "ipag-ayos",
    "mag-ayos", "magpigil", "ipigil", "ipatupad", "ipagtatalaga",
    "maglupa", "hatiin", "pagsamahin", "magbigay", "paghati",
    # English
    "fix", "repair", "clean", "replace", "provide", "release", "issue", "build",
    "install", "improve", "upgrade", "add", "schedule", "publish", "clarify",
    "implement", "enforce", "remove", "deliver", "include", "restore",
    "allocate", "appoint", "dispatch", "respond", "act on",
]

# --- strong request frames: these imply an action on their own --------------
# "kailangan namin ng birth certificate" has no action VERB, but it is plainly a
# request for the agency to issue one. These frames carry that meaning.
STRONG_REQUEST_FRAMES = [
    "dapat", "kailangan", "need to", "should", "ought to", "would like to",
    "humingi", "ipagbigay", "ipagkaloob", "ipag-issue", "ipai-issue",
    "ipagbibigay", "ipapasa", "ipinapayong", "nais kong", "gusto kong",
    "ipinakita", "hihingiin ko", "ipinihingi ko",
]

# --- action objects: WHAT the action would be about ------------------------
ACTION_OBJECTS = [
    # infrastructure / roads
    "kalsada", "kalsadang", "kalsada sa", "tulay", "drainage", "drain", "kanal",
    "poso", "water pipe", "streetlight", "lamp", "kalye", "kalsada sa baryo",
    "lagyan", "rambol", "median", "traffic", "signal", "sirens", "bumps",
    # sanitation / environment
    "basura", "garbage", "landfill", "waste", "seguridad", "toxic", "flood",
    "lindol", "bagyo", "typhoon", "weather", "bulusan", "disaster", "evacuation",
    "shelter", "relief", "food", "presyo ng", "inflation",
    # education
    "eskwela", "school", "klase", "class", "kwalipikasyon", "regularidad",
    "enrollment", "enlistment", "modules", "teacher", "mga mag-aaral", "student",
    "graduation", "scholarship", "ipon", "pambayad",
    # health
    "ospital", "hospital", "doctor", "nurse", "gamot", "medicine", "vaccine",
    "vaccination", "quarantine", "clinic", "health center", "surgery", "checkup",
    "blood", "lab", "laboratory", "mental health", "4ps",
    # social welfare / livelihood
    "social welfare", "ayuda", "tulong", " livelihood", "trabaho", "job",
    "employment", "business permit", "zoning", "sPermit", "permit",
    # transactions / services
    "permit", "clearance", "birth certificate", "marriage", "id", "passport",
    "license", "driver", "sss", "philhealth", "tax", "bayad", "payment",
    "queue", "pila", "line", "appointment", "schedule", "hotline", "complaint",
    "response", "website", "app", "online", "portal", "gcash", "cashless",
    "budget", "fund", "allocation", "salary", "allowance", "benefit",
    # general civic
    "service", "program", "action", "assistance", "help", "infrastructure",
    "implement", "guidelines", "policy", "coordination",
    # English objects
    "road", "street", "bridge", "canal", "sidewalk", "streetlight", "signage",
    "garbage", "waste", "trash", "landfill", "flood", "drain", "water",
    "electricity", "power outage", "internet", "wifi", "signal",
    "school", "class schedule", "enrollment", "teacher", "student", "modules",
    "hospital", "doctor", "nurse", "medicine", "vaccine", "vaccination",
    "clinic", "checkup", "laboratory", "mental health",
    "job", "livelihood", "employment", "business permit", "housing",
    "permit", "clearance", "passport", "driver", "license",
    "bus", "jeepney", "tricycle", "terminal", "airport", "ferry",
    "appointment", "schedule", "queue", "website", "app", "online", "portal",
    "payment", "budget", "fund", "allocation", "salary", "allowance", "benefit",
    "hotline", "complaint", "response", "relief", "evacuation", "shelter",
    "food", "security", "crime", "traffic enforcer",
]

# --- complaint without a proposed remedy ------------------------------------
COMPLAINT_MARKERS = [
    "ang pangit", "pangit ng", "masyado", "kahinaan", "nang-iingit", "naiinip",
    "kulangg", "kulang", "sirado", "sara", "bumaon", "masira", "maputi",
    "napaka", "sobrang", "grabe ang", "nang walang", "wala nang", "walang",
    "bangsay", "baha", "pumutok", "nasira", "sira", "sira ng", "lumabo",
    "ngayon lang", "hanggang ngayon", "bakit hindi", "bakit wala", "bakit walang",
    "sucks", "terrible", "awful", "useless", "garbage", "worst", "poor service",
    "bad service", "incompetent", "corrupt", "maling", "sabo",
]

# --- gratitude / pure reaction ----------------------------------------------
THANKS_MARKERS = [
    "salamat", "salamat po", "maraming salamat", "thanks", "thank you", "tnx",
    "thank u", "appreciate", "gratitude", "best regards", "good job",
]
REACTION_MARKERS = [
    "haha", "hahaha", "lol", "amen", "tang a", "tanga", "wild", "tampo",
    "grabe", "amazing", "nice one", "solid", "kudos", "salamat sa lord",
    "baka nga", "maka aya", "closure", "legit", "true", "same here",
]

# --- information question (no action requested) -----------------------------
INFO_QUESTION_MARKERS = [
    "magkano", "kailan", "saan", "sino", "bakit", "ilan", "ano ang", "ano po",
    "how much", "when", "where", "who", "why", "what is", "what are", "which",
    "is there", "are there", "can i ask", "just curious", "just want to know",
]

# --- explicit refusal to request --------------------------------------------
REFUSAL_MARKERS = [
    "hindi po ako nagbibingi", "hindi ako nagbibingi", "hindi ko po kailangan",
    "just informing", "just sharing", "not a complaint", "no request",
    "informational lang", "itutong lang",
]

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Cues:
    """Signals extracted from one comment. Evidence only — not a decision."""

    request_marker: list = field(default_factory=list)
    action_verb: list = field(default_factory=list)
    strong_frame: list = field(default_factory=list)
    action_object: list = field(default_factory=list)
    complaint: list = field(default_factory=list)
    thanks: list = field(default_factory=list)
    reaction: list = field(default_factory=list)
    info_question: list = field(default_factory=list)
    refusal: list = field(default_factory=list)
    negated: bool = False
    n_tokens: int = 0

    def as_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v}


@dataclass
class Suggestion:
    """A proposed label plus the reasoning and how sure we are."""

    label: int
    confidence: float
    rule: str
    evidence: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Stage 1 — cue extraction
# ---------------------------------------------------------------------------


def normalise(text: str) -> str:
    """Lowercase, NFC, collapse whitespace. Kept separate from the dataset's
    own normalization (GUIDELINES / contract 6.2) — this is only for matching."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text).lower()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _find(text: str, needles: Iterable[str]) -> list:
    hits = []
    for n in needles:
        if n in text:
            hits.append(n.strip())
    return hits


def extract_cues(comment_text: str, post_text: str = "") -> Cues:
    """Pull signals out of the comment (and, weakly, the post)."""
    text = normalise(comment_text)

    # A negation anywhere near a request marker usually kills the request.
    negated = bool(re.search(r"\b(hindi|hindi\s+po|ayaw|wag)\b.{0,25}\b("
                             r"pagbibingi|kailangan|ayusin|dapat|please)\b", text))

    return Cues(
        request_marker=_find(text, REQUEST_MARKERS),
        action_verb=_find(text, ACTION_VERBS),
        strong_frame=_find(text, STRONG_REQUEST_FRAMES),
        action_object=_find(text, ACTION_OBJECTS),
        complaint=_find(text, COMPLAINT_MARKERS),
        thanks=_find(text, THANKS_MARKERS),
        reaction=_find(text, REACTION_MARKERS),
        info_question=_find(text, INFO_QUESTION_MARKERS),
        refusal=_find(text, REFUSAL_MARKERS),
        negated=negated,
        n_tokens=len(text.split()),
    )


# ---------------------------------------------------------------------------
# Stage 2 — heuristic scoring
# ---------------------------------------------------------------------------


def score(cues: Cues) -> Suggestion:
    """Turn cues into a suggested label.

    The decision order matters and mirrors the decision tree in GUIDELINES 4.
    """
    ev: list = []

    # 0. Explicit refusal / pure information note.
    if cues.refusal:
        return Suggestion(LABEL_OTHER, 0.90, "refusal_marker", cues.refusal)

    # 1. A request marker together with an action verb, or a strong request
    #    frame ("kailangan", "dapat", "need to") together with an action object.
    #    NOTE: a weak marker with only an object and no frame ("Sana maayos ang
    #    kalsada") is deliberately NOT decided here. That is the single most
    #    disputed class in the guidelines (5.3 #35 vs #36), so it goes to
    #    adjudication.
    if cues.request_marker and cues.action_verb:
        ev += cues.request_marker + cues.action_verb + cues.action_object
        conf = 0.90 if cues.action_object else 0.85
        return Suggestion(LABEL_ACTIONABLE, conf, "request_marker + action_verb", ev)

    if cues.strong_frame and cues.action_object:
        ev += cues.strong_frame + cues.action_object
        return Suggestion(LABEL_ACTIONABLE, 0.88, "strong_frame + action_object", ev)

    if cues.request_marker and cues.action_object:
        ev += cues.request_marker + cues.action_object
        return Suggestion(LABEL_ACTIONABLE, 0.60, "request_marker + object_only", ev)

    if cues.strong_frame and not cues.negated:
        ev += cues.strong_frame
        return Suggestion(LABEL_ACTIONABLE, 0.80, "strong_frame_only", ev)

    # 2. An action verb on its own, in a prescriptive frame.
    if cues.action_verb and not cues.negated:
        ev += cues.action_verb
        return Suggestion(LABEL_ACTIONABLE, 0.78, "action_verb_only", ev)

    # 3. Gratitude or pure reaction, with no request anywhere.
    if (cues.thanks or cues.reaction) and not cues.request_marker:
        ev += cues.thanks + cues.reaction
        return Suggestion(LABEL_OTHER, 0.90, "gratitude_or_reaction", ev)

    # 4. Complaint with nothing proposed.
    if cues.complaint and not cues.request_marker and not cues.action_verb:
        ev += cues.complaint
        return Suggestion(LABEL_OTHER, 0.88, "complaint_without_remedy", ev)

    # 5. Information question with no action requested.
    if cues.info_question and not cues.request_marker and not cues.action_verb:
        ev += cues.info_question
        return Suggestion(LABEL_OTHER, 0.85, "information_question", ev)

    # 6. Everything else is genuinely ambiguous -> a human/agent has to look.
    ev += cues.request_marker + cues.complaint + cues.info_question
    return Suggestion(LABEL_OTHER, 0.0, "needs_adjudication", ev)


# ---------------------------------------------------------------------------
# Stage 3 — review export
# ---------------------------------------------------------------------------


def build_review_batches(rows: list, batch_size: int, out_dir: str) -> dict:
    """Write the rows that need adjudication to JSONL batches.

    Each batch carries the comment, the post context and the parent comment,
    because GUIDELINES 8.3 requires the annotator to see post context.
    """
    os.makedirs(out_dir, exist_ok=True)

    uncertain = [r for r in rows if r["confidence"] < CONFIDENCE_THRESHOLD]

    # Random audit sample of the confident rows, for verification.
    confident = [r for r in rows if r["confidence"] >= CONFIDENCE_THRESHOLD]
    rng = random.Random(RANDOM_SEED)
    rng.shuffle(confident)
    n_audit = min(len(confident), max(1, int(round(len(confident) * AUDIT_SAMPLE_RATE))))
    audit = confident[:n_audit]
    audit_ids = {r["comment_id"] for r in audit}

    work = uncertain + audit
    work.sort(key=lambda r: (r["confidence"], r["comment_id"]))

    batches = []
    for i in range(0, len(work), batch_size):
        chunk = work[i : i + batch_size]
        name = f"batch_{i // batch_size + 1:03d}.jsonl"
        path = os.path.join(out_dir, name)
        with open(path, "w", encoding="utf-8") as fh:
            for r in chunk:
                fh.write(json.dumps({
                    "comment_id": r["comment_id"],
                    "comment_text": r.get("comment_text", ""),
                    "post_text": r.get("post_text", ""),
                    "parent_comment_text": r.get("parent_comment_text", ""),
                    "is_reply": r.get("is_reply", "false"),
                    "heuristic_label": r["label"],
                    "heuristic_confidence": r["confidence"],
                    "heuristic_rule": r["rule"],
                    "heuristic_evidence": r["evidence"],
                    "review_kind": "audit" if r["comment_id"] in audit_ids else "uncertain",
                }, ensure_ascii=False) + "\n")
        batches.append({"file": name, "rows": len(chunk)})

    manifest = {
        "batches": batches,
        "n_uncertain": len(uncertain),
        "n_audit": len(audit),
        "n_auto_labelled": len(confident) - len(audit),
        "n_auto_labelled_confident": len(confident),
        "confidence_threshold": CONFIDENCE_THRESHOLD,
        "audit_sample_rate": AUDIT_SAMPLE_RATE,
        "random_seed": RANDOM_SEED,
        "total_rows": len(rows),
    }
    with open(os.path.join(out_dir, "_manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    return manifest


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------


def read_rows(path: str) -> list:
    with open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def write_rows(path: str, rows: list, fieldnames: list) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_score(args) -> int:
    rows = read_rows(args.pool)
    out = []
    for r in rows:
        cues = extract_cues(r.get("comment_text_norm") or r.get("comment_text", ""),
                            r.get("post_text", ""))
        s = score(cues)
        row = dict(r)
        row["label"] = s.label
        row["confidence"] = round(s.confidence, 3)
        row["rule"] = s.rule
        row["evidence"] = "; ".join(s.evidence)
        row["cues"] = json.dumps(cues.as_dict(), ensure_ascii=False)
        out.append(row)

    fieldnames = list(rows[0].keys()) if rows else []
    for extra in ("label", "confidence", "rule", "evidence", "cues"):
        if extra not in fieldnames:
            fieldnames.append(extra)
    write_rows(args.out, out, fieldnames)

    n_conf = sum(1 for r in out if r["confidence"] >= CONFIDENCE_THRESHOLD)
    print(f"scored {len(out)} rows")
    print(f"  confident (>= {CONFIDENCE_THRESHOLD}): {n_conf}")
    print(f"  needs adjudication:                {len(out) - n_conf}")
    print(f"  -> {args.out}")

    if args.review_out:
        m = build_review_batches(out, args.batch_size, args.review_out)
        print(f"  review batches: {len(m['batches'])} "
              f"({m['n_uncertain']} uncertain + {m['n_audit']} audit) -> {args.review_out}")
    return 0


def cmd_apply(args) -> int:
    """Merge adjudicated decisions over the heuristic scores."""
    scored = read_rows(args.scored)
    decisions = {}
    if os.path.exists(args.decisions):
        with open(args.decisions, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                decisions[d["comment_id"]] = d

    applied = 0
    for r in scored:
        d = decisions.get(r["comment_id"])
        if d is None:
            continue
        r["label"] = int(d["label"])
        r["label_str"] = "actionable" if int(d["label"]) == 1 else "other"
        r["confidence"] = 1.0
        r["rule"] = "adjudicated"
        r["evidence"] = d.get("note", "")
        r["verification"] = d.get("verification", "auto")
        if d.get("language"):
            r["language"] = d["language"]
        applied += 1

    # Map the scoring provenance onto the contract's annotation columns.
    for r in scored:
        # label_str and verification are set for EVERY row, not just adjudicated ones.
        try:
            lab = int(r.get("label", 0))
        except (TypeError, ValueError):
            lab = 0
        r["label"] = lab
        r["label_str"] = "actionable" if lab == 1 else "other"
        if not r.get("verification"):
            r["verification"] = "auto"
        r["annotation_rule"] = r.get("rule", "")
        r["annotation_evidence"] = r.get("evidence", "")
        try:
            r["annotation_confidence"] = float(r.get("confidence", 0) or 0)
        except (TypeError, ValueError):
            r["annotation_confidence"] = 0.0

    # Write ONLY the contract columns. The scoring detail (confidence, rule,
    # evidence, cues) stays in the scored file, not in the delivered dataset.
    fieldnames = list(scored[0].keys()) if scored else []
    for extra in ("label_str", "verification",
                  "annotation_rule", "annotation_evidence", "annotation_confidence"):
        if extra not in fieldnames:
            fieldnames.append(extra)
    drop = {"confidence", "rule", "evidence", "cues"}
    fieldnames = [f for f in fieldnames if f not in drop]
    write_rows(args.out, scored, fieldnames)

    n_total = len(scored)
    # Only rows the heuristic could NOT decide need adjudication. Confident rows
    # legitimately keep their heuristic label without a decision.
    still_open = [
        r for r in scored
        if float(r.get("confidence", 0) or 0) < CONFIDENCE_THRESHOLD
        and r.get("rule") != "adjudicated"
    ]
    n_auto = sum(1 for r in scored
                 if float(r.get("confidence", 0) or 0) >= CONFIDENCE_THRESHOLD)
    print(f"wrote {n_total} rows to {args.out}")
    print(f"  adjudicated decisions applied:           {applied}")
    print(f"  auto-decided (confident, no decision needed): {n_auto}")
    print(f"  still awaiting adjudication:              {len(still_open)}")
    if still_open:
        print("  WARNING: these rows are below threshold and have no decision. "
              "They block release.")
        for r in still_open[:5]:
            print(f"    {r.get('comment_id')}  conf={r.get('confidence')}  {r.get('rule')}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("score", help="score the pool and export review batches")
    s.add_argument("--pool", required=True)
    s.add_argument("--out", required=True)
    s.add_argument("--review-out", default=None)
    s.add_argument("--batch-size", type=int, default=50)
    s.set_defaults(func=cmd_score)

    a = sub.add_parser("apply", help="merge adjudicated decisions into the dataset")
    a.add_argument("--scored", required=True)
    a.add_argument("--decisions", required=True)
    a.add_argument("--out", required=True)
    a.set_defaults(func=cmd_apply)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
