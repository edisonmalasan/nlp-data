"""
language_consistency.py — find the rows that got inconsistent labels.

The re-label applies ONE convention to every row, but a convention with hard
families can still be applied inconsistently: the same template gets `fil` on
one row and `mixed` on another. That is exactly the kind of noise the
re-label was meant to remove, so it is checked for rather than assumed away.

Rows that share a template - the same opening words, the same shape - are
grouped, and a group is flagged when it received more than one label.

    python tools/language_consistency.py
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


def template(text):
    """A coarse shape for a comment, so the same kind of comment groups."""
    t = (text or "").lower().strip()
    t = re.sub(r"[^a-z0-9\s']", " ", t)
    words = t.split()
    if not words:
        return "<empty>"
    # the first two content words, plus the shape of the rest
    stop = {"po", "ba", "naman", "sana", "dapat", "kailangan", "yung", "ang",
            "ng", "sa", "mga", "at", "ko", "po", "ay", "rin", "din", "lang",
            "kung", "may", "ito", "natin", "ninyo", "namin", "kayo", "ako",
            "ikaw", "sila", "kami", "tayo", "hindi", "para", "kasi", "baka",
            "daw", "raw", "tapos", "kung", "eh", "yup", "opo", "sige", "ba",
            "nag", "na", "pa", "da", "di", "ni", "si", "kay", "nang", "nka"}
    content = [w for w in words if w not in stop]
    head = " ".join(content[:2]) if content else " ".join(words[:2])
    return f"{head} :: {len(content)} content words"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check the language labels for consistency")
    ap.add_argument("--min-group", type=int, default=3)
    args = ap.parse_args(argv)

    labels = {}
    for f in sorted(os.listdir(BATCHES)):
        if not (f.startswith("out_") and f.endswith(".jsonl")):
            continue
        for line in io.open(os.path.join(BATCHES, f), encoding="utf-8"):
            if line.strip():
                d = json.loads(line)
                labels[d["comment_id"]] = d["language"]

    print(f"language labels read: {len(labels)}")
    if not labels:
        return 1
    print("  " + str(dict(Counter(labels.values()))))

    text = {}
    for r in csv.DictReader(io.open(POOL, encoding="utf-8", newline="")):
        text[r["comment_id"]] = r.get("comment_text_norm") or ""

    groups = defaultdict(list)
    for cid, lang in labels.items():
        groups[template(text.get(cid, ""))].append((cid, lang))

    inconsistent = []
    for tpl, members in groups.items():
        if len(members) < args.min_group:
            continue
        c = Counter(l for _, l in members)
        if len(c) > 1:
            inconsistent.append((tpl, members, c))

    print(f"\ngroups of {args.min_group}+ rows that received more than one label: "
          f"{len(inconsistent)}")
    for tpl, members, c in sorted(inconsistent, key=lambda x: -len(x[1]))[:14]:
        print(f"\n  {tpl}  {dict(c)}")
        for cid, lang in members[:6]:
            print(f"     {lang:6} {cid[:26]:28} {text.get(cid,'')[:72]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
