"""
audit.py — is the delivered data the data the study needs?

Checks the released dataset against the scope in docs/NLP-Final-Paper.pdf and
docs/NLP-PLAN.pdf:

  1. the frame: national government agency pages, Facebook only
  2. the label definition: does an `actionable` comment actually propose or
     request an identifiable action?
  3. the research question: the dataset must contain actionable comments WITH
     and WITHOUT politeness markers, and other comments WITH and WITHOUT
     them. If the actionable class is almost all marker-bearing, the study's
     answer is trivially yes and the dataset is wrong for the question.
  4. the label pairing: the paper's own worked examples
  5. privacy: no author name left in the text
  6. the post context: is the caption the post's caption?
"""

import csv
import io
import json
import os
import re
import sys
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DS = os.path.join(ROOT, "data", "processed", "dataset_v1.csv")
EXT = os.path.join(ROOT, "data", "processed", "dataset_v1_ext.csv")
REG = os.path.join(ROOT, "data", "provenance", "government_agencies.csv")

# the suggestion-related features the paper's proposed model uses
MARKERS = ["please", "dapat", "sana", "paki"]
MARKER_RE = re.compile(r"\b(please|dapat|sana|paki\w*)\b", re.I)


def read(path):
    with io.open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def has_marker(text):
    return bool(MARKER_RE.search(text or ""))


def main():
    ds = read(DS)
    ext = read(EXT)
    reg = read(REG)
    n = len(ds)
    print("=" * 74)
    print("AUDIT AGAINST THE SCOPE IN docs/NLP-Final-Paper.pdf")
    print("=" * 74)

    # ---------------------------------------------------------------- 1
    print("\n1. THE FRAME")
    print(f"   primary rows                : {n}")
    print(f"   primary platforms           : {dict(Counter(r['platform'] for r in ds))}")
    print(f"   source accounts (primary)   : {len({r['source_page'] for r in ds})}")
    print(f"   distinct posts              : {len({r['post_id'] for r in ds})}")
    print(f"   languages                   : {dict(Counter(r['language'] for r in ds))}")
    print(f"   label 1 / label 0           : {sum(1 for r in ds if r['label']=='1')} / "
          f"{sum(1 for r in ds if r['label']=='0')}")

    # every source account must be a registered agency, and no LGU
    reg_by_page = {r["source_page"]: r for r in reg if r["platform"] == "facebook"}
    missing = [r["source_page"] for r in ds if r["source_page"] not in reg_by_page]
    lgu = [r["source_page"] for r in ds
           if reg_by_page.get(r["source_page"], {}).get("agency_type")
           == "local_government_unit"]
    print(f"   accounts not in the registry : {len(set(missing))} {sorted(set(missing))[:5]}")
    print(f"   local government units      : {len(set(lgu))} (the scope is NATIONAL)")
    types = Counter(reg_by_page.get(r["source_page"], {}).get("agency_type", "?")
                    for r in ds)
    print(f"   agency types                : {dict(types)}")

    # ---------------------------------------------------------------- 3
    print("\n3. THE RESEARCH QUESTION - the critical check")
    print("   The RQ asks whether adding 'please/dapat/sana/paki-' features")
    print("   improves on a TF-IDF baseline. That is only answerable if the")
    print("   dataset contains all four combinations.")
    print()
    grid = defaultdict(int)
    for r in ds:
        grid[(r["label"], has_marker(r.get("comment_text_norm")))] += 1
    a_m = grid[("1", True)]
    a_n = grid[("1", False)]
    o_m = grid[("0", True)]
    o_n = grid[("0", False)]
    print(f"   {'class':10} {'with a marker':>16} {'without':>10}")
    print(f"   {'actionable':10} {a_m:>10} ({a_m/max(a_m+a_n,1):5.1%}) {a_n:>7} ({a_n/max(a_m+a_n,1):5.1%})")
    print(f"   {'other':10} {o_m:>10} ({o_m/max(o_m+o_n,1):5.1%}) {o_n:>7} ({o_n/max(o_m+o_n,1):5.1%})")
    print()
    ok = a_m > 20 and a_n > 20 and o_m > 20 and o_n > 20
    print(f"   all four cells populated      : {'YES' if ok else 'NO - a cell is too thin'}")
    print(f"   actionable WITHOUT a marker   : {a_n} ({a_n/max(a_m+a_n,1):.1%})")
    print(f"   other WITH a marker           : {o_m} ({o_m/max(o_m+o_n,1):.1%})")
    print()
    print("   Per marker, the share of the rows that carry it:")
    for m in MARKERS:
        withm = [r for r in ds if re.search(r"\b" + m + r"\w*\b", r.get("comment_text_norm", ""), re.I)]
        if not withm:
            print(f"     {m:9} 0 rows")
            continue
        ones = sum(1 for r in withm if r["label"] == "1")
        print(f"     {m:9} {len(withm):>5} rows, {ones/max(len(withm),1):5.1%} of them actionable")

    # ---------------------------------------------------------------- 2
    print("\n2. THE LABEL DEFINITION - do the actionable rows really request an action?")
    print("   A sample of label 1, read as a reviewer would read them:")
    import random
    rng = random.Random(11)
    ones = [r for r in ds if r["label"] == "1"]
    for r in rng.sample(ones, min(14, len(ones))):
        t = (r.get("comment_text_norm") or "")[:105]
        print(f"     [{r['source_page'][:16]:16}] {t!r}")

    print("\n   A sample of label 0:")
    zeros = [r for r in ds if r["label"] == "0"]
    for r in rng.sample(zeros, min(10, len(zeros))):
        t = (r.get("comment_text_norm") or "")[:105]
        print(f"     [{r['source_page'][:16]:16}] {t!r}")

    # ---------------------------------------------------------------- 4
    print("\n4. THE PAPER'S OWN WORKED EXAMPLES")
    checks = [
        ("Ang pangit ng kalsada namin", 0),
        ("Please repair the damaged road in our barangay", 1),
        ("Dapat ayusin ang drainage", 1),
        ("Please po, clean the canal", 1),
    ]
    from importlib import util
    # the annotator is a script, not a package, and it uses a dataclass, so
    # it has to be imported the way it is meant to be run
    ann_path = os.path.join(ROOT, "src", "annotate", "auto_annotator.py")
    import subprocess
    script = (
        "import sys, json\n"
        f"sys.path.insert(0, {os.path.join(ROOT, 'src', 'annotate')!r})\n"
        "import auto_annotator as a\n"
        "out = []\n"
        "for t in json.loads(sys.argv[1]):\n"
        "    c = a.extract_cues(t, '')\n"
        "    lab, conf, rule = a.score(c)\n"
        "    out.append([lab, conf, rule])\n"
        "print(json.dumps(out))\n"
    )
    texts = [c[0] for c in checks]
    r = subprocess.run([sys.executable, "-c", script, json.dumps(texts)],
                       cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    try:
        results = json.loads(r.stdout.strip().splitlines()[-1])
    except Exception:
        results = []
        print("   (the engine could not be run:", r.stderr.strip()[:120], ")")
    for (text, want), got in zip(checks, results):
        mark = "ok " if got[0] == want else "!! "
        print(f"   {mark}{text[:48]:50} engine={got[0]} (want {want}) "
              f"conf={got[1]:.2f} {got[2]}")

    # ---------------------------------------------------------------- 5
    print("\n5. PRIVACY - is an author's name left in the text?")
    # the extractor stores the author separately, but the name can appear
    # inside the comment text itself
    name_in_text = 0
    for r in ds:
        t = r.get("comment_text_norm") or ""
        if len(t.split()) <= 6 and t:
            name_in_text += 1
    print(f"   rows whose text is 6 words or fewer : {name_in_text} "
          f"({name_in_text/n:.1%}) - these are mostly check-in names")
    pii = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+|\b09\d{9}\b|\b(\+63|63)\d{10}\b")
    hits = [r["comment_id"] for r in ds if pii.search(r.get("comment_text_norm", ""))]
    print(f"   rows with an email or phone number  : {len(hits)} {hits[:4]}")
    named = [r for r in ds if (r.get("comment_text_norm") or "").count(" ") <= 3
             and re.match(r"^[A-Z][a-z]+ [A-Z]", r.get("comment_text_norm") or "")]
    print(f"   rows that look like a bare full name : {len(named)}")

    # ---------------------------------------------------------------- 6
    print("\n6. THE POST CONTEXT - is the caption the post's caption?")
    empty = sum(1 for r in ds if not (r.get("post_text") or "").strip())
    print(f"   rows with no post caption            : {empty} ({empty/n:.1%})")
    # a caption that begins with a commenter name is a comment, not a caption
    suspect = 0
    for r in ds:
        t = (r.get("post_text") or "").strip()
        if t and re.match(r"^[A-Z][a-z]+ [A-Z][a-z]+ ", t) and len(t) < 300:
            suspect += 1
    print(f"   captions that look like a comment     : {suspect} ({suspect/n:.1%})")
    posts = defaultdict(set)
    for r in ds:
        posts[r["post_id"]].add((r.get("post_text") or "").strip())
    inconsistent = sum(1 for v in posts.values() if len(v) > 1)
    print(f"   posts with inconsistent captions      : {inconsistent} of {len(posts)}")

    # ----------------------------------------------------------------
    print("\n" + "=" * 74)
    print("SUMMARY")
    print("=" * 74)
    print(f"  primary dataset        : {n} Facebook comments, 2 classes, "
          f"{n/max(1,len({r['post_id'] for r in ds}))} posts")
    print(f"  actionable rate        : {sum(1 for r in ds if r['label']=='1')/n:.1%}")
    print(f"  the four RQ cells      : "
          f"{'all populated' if ok else 'TOO THIN'}")
    print(f"  privacy                : {len(hits)} email/phone hits")
    print(f"  post context quality   : {empty/n:.0%} empty, {suspect/n:.0%} suspect")
    return 0


if __name__ == "__main__":
    sys.exit(main())
