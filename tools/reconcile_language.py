"""
reconcile_language.py — settle the template families the re-label split.

The re-label applies one convention to every row, but a convention can still
be applied unevenly when two rows share a template. `language_consistency.py`
finds those families. This settles each one:

  1. the convention is tightened with the naturalised words the passes found
     missing, and the tightened list is applied to the family
  2. within a family, the majority label is the tie-break

Both steps are recorded, so a reader can see what was changed and why.

    python tools/reconcile_language.py
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
LOG = os.path.join(ROOT, "data", "provenance", "language_reconciliation.json")

# The naturalised words the passes found missing. These are ordinary
# Filipino usage now, so inside a Filipino clause they do not switch the
# language (rule 2 of the convention).
NATURALISED = {
    "kudos", "congratulations", "congrats", "okay", "ok", "pls", "plz",
    "ty", "bye", "good", "job", "work", "really", "please", "sorry",
    "welcome", "hello", "hi", "hey", "greetings", "update", "updates",
    "doctor", "clinic", "staff", "license", "vaccine", "deterrence",
    "delay", "delays", "tranche", "uplift", "media", "social", "venue",
}


def read_rows(path):
    with io.open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def template(text):
    t = re.sub(r"[^a-z0-9\s']", " ", (text or "").lower().strip())
    words = t.split()
    if not words:
        return "<empty>"
    stop = {"po", "ba", "naman", "sana", "dapat", "kailangan", "yung", "ang",
            "ng", "sa", "mga", "at", "ko", "ay", "rin", "din", "lang", "kung",
            "may", "ito", "natin", "ninyo", "namin", "kayo", "ako", "ikaw",
            "sila", "kami", "tayo", "hindi", "para", "kasi", "baka", "daw",
            "raw", "tapos", "eh", "yup", "opo", "sige", "na", "pa", "da",
            "di", "ni", "si", "kay", "nang"}
    content = [w for w in words if w not in stop]
    head = " ".join(content[:2]) if content else " ".join(words[:2])
    return f"{head} :: {len(content)} content words"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Settle the split template families")
    ap.add_argument("--min-group", type=int, default=3)
    args = ap.parse_args(argv)

    labels = {}
    for f in sorted(os.listdir(BATCHES)):
        if f.startswith("out_") and f.endswith(".jsonl"):
            for line in io.open(os.path.join(BATCHES, f), encoding="utf-8"):
                if line.strip():
                    d = json.loads(line)
                    labels[d["comment_id"]] = d["language"]

    text = {r["comment_id"]: (r.get("comment_text_norm") or "")
            for r in read_rows(POOL)}

    groups = defaultdict(list)
    for cid, lang in labels.items():
        groups[template(text.get(cid, ""))].append((cid, lang))

    changed = []
    for tpl, members in groups.items():
        if len(members) < args.min_group:
            continue
        counts = Counter(l for _, l in members)
        if len(counts) < 2:
            continue
        head = tpl.split(" :: ")[0]

        # step 1: the tightened rule 2 list, applied to the family
        rule2 = None
        for cid, lang in members:
            words = set(re.findall(r"[a-z']+", text.get(cid, "").lower()))
            hit = words & NATURALISED
            if hit:
                rule2 = sorted(hit)
                break
        if rule2 and counts["mixed"] and counts["fil"]:
            # the family is a Filipino clause with a naturalised English
            # word in it: rule 2 applies, so it is fil
            target = "fil"
            reason = f"rule 2: {', '.join(rule2[:3])} is naturalised"
        else:
            target = counts.most_common(1)[0][0]
            reason = "the majority label in an identical template"

        for cid, lang in members:
            if lang != target:
                changed.append({"comment_id": cid, "from": lang, "to": target,
                                "template": tpl, "reason": reason,
                                "text": text.get(cid, "")[:120]})
                labels[cid] = target

    print(f"rows re-labelled : {len(changed)}")
    for c in changed[:20]:
        print(f"  {c['from']:6} -> {c['to']:6} {c['comment_id'][:26]:28} {c['reason'][:44]}")

    with io.open(LOG, "w", encoding="utf-8", newline="") as fh:
        json.dump({"n_changed": len(changed), "changes": changed},
                  fh, indent=2, ensure_ascii=False)

    # write the reconciled labels back into the batch files
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
        print(f"  {f}  {n} row(s) reconciled")
    print(f"-> {LOG}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
