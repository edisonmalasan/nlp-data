"""
apply_rule2a.py — settle the compound families with rule 2a.

Rule 2a: a compound of two naturalised words is still naturalised, so it
does not create a mix. A compound is an English phrase only when at least
one of its words is not naturalised.

This finds the comments that contain such a compound and applies the rule
to them, and the comments that contain a compound with a non-naturalised
word. The changes are recorded.

    python tools/apply_rule2a.py
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BATCHES = os.path.join(ROOT, "data", "interim", "lang_batches")
POOL = os.path.join(ROOT, "data", "processed", "dataset_v1.csv")
LOG = os.path.join(ROOT, "data", "provenance", "language_rule2a.json")

# the naturalised words, rule 2 and rule 2a
NATURALISED = {
    "budget", "schedule", "form", "deadline", "service", "services",
    "office", "branch", "request", "program", "programme", "project",
    "projects", "facility", "facilities", "checklist", "valid",
    "requirements", "update", "updates", "drainage", "traffic", "doctor",
    "clinic", "staff", "license", "vaccine", "deterrence", "delay",
    "tranche", "uplift", "kudos", "congratulations", "congrats", "sorry",
    "welcome", "hello", "hi", "hey", "good", "job", "work", "works",
    "really", "okay", "ok", "pls", "plz", "ty", "bye", "media", "social",
    "venue", "road", "roads", "improvement", "improvements",
    "infrastructure", "coordination", "monitoring", "inspection",
    "department", "government", "public", "local", "goods", "civil",
    "society", "private", "sector", "commuters", "motorcyclists",
    "komyuter", "motorista", "restoration", "materials", "teacher",
    "teachers", "classroom", "classrooms", "aircon", "health", "grade",
    "homework", "leadership", "politics", "hotmeal", "fake", "consent",
    "waiver", "prevention", "side", "effects", "dosage", "post", "page",
    "truck", "trucks", "equipment", "quarry", "relief", "development",
    "progress", "effort", "audience", "auditor", "official",
}

STOP = {
    "ang", "ng", "sa", "mga", "at", "po", "ba", "naman", "sana", "dapat",
    "kailangan", "yung", "ko", "ay", "rin", "din", "lang", "kung", "may",
    "ito", "natin", "ninyo", "namin", "kayo", "ako", "ikaw", "sila", "kami",
    "tayo", "hindi", "para", "kasi", "baka", "daw", "raw", "tapos", "eh",
    "yup", "opo", "sige", "na", "pa", "da", "di", "ni", "si", "kay", "nang",
    "the", "a", "an", "of", "in", "to", "for", "is", "are", "was", "and",
    "that", "this", "it", "with", "on", "by", "not", "have", "has",
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Apply rule 2a to the compound families")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args(argv)

    labels = {}
    for f in sorted(os.listdir(BATCHES)):
        if f.startswith("out_") and f.endswith(".jsonl"):
            for line in io.open(os.path.join(BATCHES, f), encoding="utf-8"):
                if line.strip():
                    d = json.loads(line)
                    labels[d["comment_id"]] = d["language"]

    text = {r["comment_id"]: (r.get("comment_text_norm") or "")
            for r in csv.DictReader(io.open(POOL, encoding="utf-8", newline=""))}

    changed = []
    for cid, lang in list(labels.items()):
        t = text.get(cid, "")
        if not t:
            continue
        words = re.findall(r"[a-z']+", t.lower())
        # the English compounds: two adjacent content words, neither a stop word
        compounds = []
        for i in range(len(words) - 1):
            a, b = words[i], words[i + 1]
            if a in STOP or b in STOP or len(a) < 3 or len(b) < 3:
                continue
            compounds.append((a, b))
        if not compounds:
            continue
        all_natural = all(a in NATURALISED and b in NATURALISED
                          for a, b in compounds)
        any_foreign = any((a not in NATURALISED and a not in STOP) or
                          (b not in NATURALISED and b not in STOP)
                          for a, b in compounds)
        # only act where the compound is the whole reason for the label
        if all_natural and lang == "mixed":
            changed.append({"comment_id": cid, "from": "mixed", "to": "fil",
                            "rule": "2a", "why": "every compound is naturalised",
                            "text": t[:140]})
            labels[cid] = "fil"
        elif any_foreign and lang == "fil" and len(compounds) == 1:
            a, b = compounds[0]
            foreign = a if a not in NATURALISED else b
            changed.append({"comment_id": cid, "from": "fil", "to": "mixed",
                            "rule": "2a", "why": f"{foreign!r} is not naturalised",
                            "text": t[:140]})
            labels[cid] = "mixed"

    print(f"rows changed by rule 2a: {len(changed)}")
    for c in changed[:14]:
        print(f"  {c['from']:6} -> {c['to']:6} {c['comment_id'][:24]:26} {c['why'][:40]}")

    with io.open(LOG, "w", encoding="utf-8", newline="") as fh:
        json.dump({"n_changed": len(changed), "changes": changed},
                  fh, indent=2, ensure_ascii=False)

    if args.apply:
        for f in sorted(os.listdir(BATCHES)):
            if not (f.startswith("out_") and f.endswith(".jsonl")):
                continue
            path = os.path.join(BATCHES, f)
            rows = [json.loads(l) for l in io.open(path, encoding="utf-8") if l.strip()]
            n = 0
            for r in rows:
                new = labels.get(r["comment_id"])
                if new and new != r.get("language"):
                    r["language"] = new
                    n += 1
            if n:
                with io.open(path, "w", encoding="utf-8", newline="") as fh:
                    for r in rows:
                        fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            print(f"  {f}  {n} row(s) updated")
    print(f"-> {LOG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
