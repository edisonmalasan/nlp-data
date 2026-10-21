"""
language_phrases.py — find the English phrases that got inconsistent labels.

The template check groups comments by their opening words. That misses a
different kind of split: the same English phrase appearing in two comments,
labelled differently because the surrounding text differed ("road
improvement" vs "road improvements", or the same phrase with and without a
Filipino clause beside it).

This finds the repeated English phrases and reports the ones whose comments
did not all get the same label.

    python tools/language_phrases.py
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

# the words the convention treats as ordinary Filipino usage, so a phrase
# built only from these is not an English phrase
NATURALISED = {
    "budget", "schedule", "form", "deadline", "service", "office", "branch",
    "request", "program", "project", "facility", "checklist", "valid",
    "requirements", "update", "updates", "drainage", "traffic", "doctor",
    "clinic", "staff", "license", "vaccine", "deterrence", "delay", "tranche",
    "uplift", "kudos", "congratulations", "congrats", "sorry", "welcome",
    "hello", "hi", "hey", "good", "job", "work", "really", "okay", "ok",
    "road", "improvement", "improvements", "construction", "infrastructure",
    "coordination", "monitoring", "inspection", "department", "government",
    "public", "local", "goods", "civil", "society", "private", "sector",
}


def english_phrases(text):
    """The English content bigrams in a comment."""
    words = re.findall(r"[a-z']+", (text or "").lower())
    out = set()
    for i in range(len(words) - 1):
        a, b = words[i], words[i + 1]
        if a in NATURALISED or b in NATURALISED:
            continue
        if len(a) < 3 or len(b) < 3:
            continue
        out.add(f"{a} {b}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Check the phrase-level consistency")
    ap.add_argument("--min-rows", type=int, default=3)
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

    by_phrase = defaultdict(list)
    for cid, lang in labels.items():
        for p in english_phrases(text.get(cid, "")):
            by_phrase[p].append((cid, lang))

    split = []
    for phrase, members in by_phrase.items():
        if len(members) < args.min_rows:
            continue
        c = Counter(l for _, l in members)
        if len(c) > 1:
            split.append((phrase, members, c))

    print(f"English phrases seen in {args.min_rows}+ rows: "
          f"{sum(1 for v in by_phrase.values() if len(v) >= args.min_rows)}")
    print(f"of those, labelled more than one way: {len(split)}")
    for phrase, members, c in sorted(split, key=lambda x: -len(x[1]))[:10]:
        print(f"\n  {phrase!r}  {dict(c)}")
        for cid, lang in members[:6]:
            print(f"     {lang:6} {cid[:24]:26} {text.get(cid,'')[:74]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
