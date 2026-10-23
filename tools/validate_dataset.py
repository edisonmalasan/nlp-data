"""
validate_dataset.py — Stage 5. The acceptance test.

Implements the 17 checks V-01..V-17 from DATA_CONTRACT.md 14. The dataset is
delivered only when this exits 0 with no errors.

    python tools/validate_dataset.py
    python tools/validate_dataset.py --dataset data/processed/dataset_v1.csv \\
        --outdir data/processed/splits --report data/processed/validation_report.txt

A check is never weakened to make it pass. If a check is genuinely wrong,
change it in DATA_CONTRACT.md 14 with a changelog entry, not here.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

BT = chr(96)

CONTRACT_PATH = "DATA_CONTRACT.md"

# Fallback column list, used only if the contract cannot be read. The contract
# is the source of truth: DATA_CONTRACT.md section 5.2 defines the schema, and
# a hardcoded copy here would silently drift out of order.
_FALLBACK_COLUMNS = [
    "comment_id", "platform", "source_page", "source_page_name", "agency_id", "agency",
    "agency_abbr", "post_id", "post_url", "post_date", "post_text", "comment_text",
    "comment_text_norm", "context_text_norm", "dedup_key", "n_tokens", "language", "label",
    "label_str", "annotator_id", "label_2", "agreement", "adjudicated_by",
    "adjudication_note", "guideline_version", "source_snapshot", "collected_at",
    "pii_redacted", "split", "verification", "annotation_rule",
    "annotation_evidence", "annotation_confidence", "stratum",
]


def contract_columns(path: str = CONTRACT_PATH) -> tuple:
    """Read the expected column order from DATA_CONTRACT.md section 5.2.

    Returns (columns, source) where source is "contract" or "fallback".
    """
    if not os.path.exists(path):
        return list(_FALLBACK_COLUMNS), "fallback (contract not found)"
    try:
        text = io.open(path, encoding="utf-8").read()
    except Exception:
        return list(_FALLBACK_COLUMNS), "fallback (contract unreadable)"

    m = re.search(r"### 5\.2 `dataset_v1\.csv` columns(.*?)\*\*Column groups", text, re.S)
    if not m:
        return list(_FALLBACK_COLUMNS), "fallback (section 5.2 not found)"

    cols = re.findall(r"^\|\s*(\d+)\s*\|\s*`([a-z_0-9]+)`\s*\|", m.group(1), re.M)
    if not cols:
        return list(_FALLBACK_COLUMNS), "fallback (no columns parsed)"

    nums = [int(n) for n, _ in cols]
    if nums != list(range(1, len(nums) + 1)):
        return list(_FALLBACK_COLUMNS), "fallback (contract numbering not contiguous)"

    return [c for _, c in cols], "contract"


PLATFORMS = {"facebook", "youtube", "reddit", "x"}
LANGUAGES = {"fil", "eng", "mixed"}
VERIFICATIONS = {"auto", "llm_verified", "human_verified", "human_labeled"}
COMMENT_ID_RE = re.compile(r"^[a-z]+_[a-z0-9_]+_\d{4}$")

PII_PATTERNS = {
    "url": re.compile(r"https?://|www\.", re.IGNORECASE),
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "phone": re.compile(r"(?<!\w)(?:\+?63|0)\d[\d\s\-().]{5,}\d(?!\w)"),
    "mention": re.compile(r"@[\w.$-]+"),
    "zero_width": re.compile("[\u200B-\u200F\u202A-\u202E\u2060\uFEFF]"),
}

MIN_ROWS_PRIMARY = 600
MIN_ROWS_COMBINED = 1000
MIN_PER_CLASS = 150
MIN_AGENCY_ROWS = 40
MIN_VERIFIED = 100
MIN_RELABEL_RATE = 0.20
MIN_KAPPA = 0.60
MAX_PRIOR_DRIFT = 0.10


class Report:
    def __init__(self):
        self.checks = []

    def add(self, vid, name, ok, detail=""):
        self.checks.append({"id": vid, "name": name, "ok": bool(ok), "detail": detail})
        return ok

    @property
    def errors(self):
        return [c for c in self.checks if not c["ok"]]

    def render(self):
        lines = []
        for c in self.checks:
            mark = "PASS" if c["ok"] else "FAIL"
            lines.append(f"[{mark}] {c['id']}  {c['name']}")
            if c["detail"]:
                lines.append(f"         {c['detail']}")
        n_err = len(self.errors)
        lines.append("")
        lines.append(f"{len(self.checks)} checks, {n_err} errors")
        return "\n".join(lines)


def read_csv(path: str) -> list:
    with io.open(path, encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def read_header(path: str) -> list:
    with io.open(path, encoding="utf-8", newline="") as fh:
        return next(csv.reader(fh))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Validate the dataset (V-01..V-17)")
    ap.add_argument("--dataset", default="data/processed/dataset_v1.csv")
    ap.add_argument("--outdir", default="data/processed/splits")
    ap.add_argument("--agencies", default="data/provenance/government_agencies.csv")
    ap.add_argument("--posts", default="data/processed/posts_v1.csv")
    ap.add_argument("--metadata", default="data/processed/dataset_v1.metadata.json")
    ap.add_argument("--contract", default="DATA_CONTRACT.md",
                    help="contract file the expected schema is read from")
    ap.add_argument("--report", default="data/processed/validation_report.txt")
    ap.add_argument("--min-rows", type=int, default=MIN_ROWS_PRIMARY)
    args = ap.parse_args(argv)

    rep = Report()

    expected_columns, column_source = contract_columns(args.contract)

    # ---------------- V-01 schema ----------------
    try:
        header = read_header(args.dataset)
    except FileNotFoundError:
        rep.add("V-01", "schema and file integrity", False, f"missing file: {args.dataset}")
        print(rep.render())
        return 1

    ok = header == expected_columns
    detail = f"{len(header)} columns (expected order from {column_source})"
    if not ok:
        missing = [c for c in expected_columns if c not in header]
        extra = [c for c in header if c not in expected_columns]
        detail += f"; missing={missing} extra={extra}"
        if set(header) == set(expected_columns):
            detail += " (same set, wrong order)"
        elif len(header) != len(expected_columns):
            detail += f" (expected {len(expected_columns)} columns)"
    rep.add("V-01", "schema matches the contract exactly", ok, detail)

    rows = read_csv(args.dataset)
    rep.add("V-01b", "dataset parses as CSV", True, f"{len(rows)} rows")

    # ---------------- V-02 row count ----------------
    rep.add("V-02", "row count meets the target", len(rows) >= args.min_rows,
            f"{len(rows)} rows, need >= {args.min_rows}")

    # ---------------- V-03 comment_id ----------------
    ids = [r.get("comment_id", "") for r in rows]
    bad_fmt = [i for i in ids if not COMMENT_ID_RE.match(i or "")]
    dupes = [i for i, n in Counter(ids).items() if n > 1]
    empty = [i for i in ids if not i]
    rep.add("V-03", "comment_id unique, non-null, well-formed",
            not bad_fmt and not dupes and not empty,
            f"bad_format={len(bad_fmt)} duplicates={len(dupes)} empty={len(empty)}")

    # ---------------- V-04 label encoding ----------------
    bad_label = [r.get("comment_id") for r in rows if r.get("label") not in ("0", "1")]
    bad_mirror = [r.get("comment_id") for r in rows
                  if r.get("label_str") != ("actionable" if r.get("label") == "1" else "other")]
    rep.add("V-04", "label in {0,1} and label_str agrees",
            not bad_label and not bad_mirror,
            f"bad_label={len(bad_label)} label_str_mismatch={len(bad_mirror)}")

    # ---------------- V-05 enums ----------------
    bad_plat = [r for r in rows if r.get("platform") not in PLATFORMS]
    bad_lang = [r for r in rows if r.get("language") not in LANGUAGES]
    bad_bool = [r for r in rows
                if r.get("pii_redacted") not in ("true", "false")
                or r.get("agreement") not in ("", "true", "false")]
    rep.add("V-05", "platform / language / boolean columns hold allowed values",
            not bad_plat and not bad_lang and not bad_bool,
            f"platform={len(bad_plat)} language={len(bad_lang)} bool={len(bad_bool)}")

    # ---------------- V-06 label_2 / agreement ----------------
    bad_l2 = [r for r in rows if r.get("label_2") not in ("", "0", "1")]
    bad_ag_empty = [r for r in rows
                    if (r.get("label_2") == "") != (r.get("agreement") == "")]
    bad_ag_val = [r for r in rows
                  if r.get("label_2") not in ("", None)
                  and r.get("agreement") != ("true" if r.get("label") == r.get("label_2") else "false")]
    rep.add("V-06", "label_2 and agreement are consistent",
            not bad_l2 and not bad_ag_empty and not bad_ag_val,
            f"bad_label_2={len(bad_l2)} agreement_empty_mismatch={len(bad_ag_empty)} "
            f"agreement_value_mismatch={len(bad_ag_val)}")

    # ---------------- V-07 post field consistency ----------------
    posts_path = args.posts
    post_fields = ("post_url", "post_date", "post_text")
    post_mismatch = 0
    missing_post = 0
    if os.path.exists(posts_path):
        posts = {p.get("post_id", ""): p for p in read_csv(posts_path)}
        for r in rows:
            p = posts.get(r.get("post_id", ""))
            if p is None:
                missing_post += 1
                continue
            for f in post_fields:
                if (r.get(f) or "") != (p.get(f) or ""):
                    post_mismatch += 1
        rep.add("V-07", "denormalized post fields match posts_v1.csv",
                post_mismatch == 0 and missing_post == 0,
                f"missing_post={missing_post} field_mismatches={post_mismatch}")
    else:
        rep.add("V-07", "denormalized post fields match posts_v1.csv", False,
                f"missing file: {posts_path}")

    # ---------------- V-08 text and PII leakage ----------------
    empty_norm = [r for r in rows if not (r.get("comment_text_norm") or "").strip()]
    pii_hits = Counter()
    for r in rows:
        for name, pat in PII_PATTERNS.items():
            if pat.search(r.get("comment_text_norm") or ""):
                pii_hits[name] += 1
    rep.add("V-08", "normalized text is non-empty and free of PII patterns",
            not empty_norm and not pii_hits,
            f"empty={len(empty_norm)} pii={dict(pii_hits)}")

    # ---------------- V-09 no residual exact duplicates ----------------
    keys = [r.get("dedup_key", "") for r in rows]
    nonempty = [k for k in keys if k]
    dup_keys = [k for k, n in Counter(nonempty).items() if n > 1]
    rep.add("V-09", "no residual exact duplicates", not dup_keys,
            f"{len(dup_keys)} duplicated dedup_keys")

    # ---------------- V-10 split integrity ----------------
    split_files = {s: os.path.join(args.outdir, f"{s}.csv") for s in ("train", "dev", "test")}
    missing_splits = [s for s, p in split_files.items() if not os.path.exists(p)]
    split_rows = {}
    all_split_ids = []
    for s, p in split_files.items():
        if os.path.exists(p):
            split_rows[s] = read_csv(p)
            all_split_ids += [r.get("comment_id", "") for r in split_rows[s]]
    col_mismatch = []
    for s, bucket in split_rows.items():
        for r in bucket:
            ds = next((x for x in rows if x.get("comment_id") == r.get("comment_id")), None)
            if ds is None:
                continue
            if (ds.get("split") or "") != s:
                col_mismatch.append(r.get("comment_id"))
    dup_split = [i for i, n in Counter(all_split_ids).items() if n > 1]
    rep.add("V-10", "split files exist, are disjoint, and match the split column",
            not missing_splits and not col_mismatch and not dup_split,
            f"missing={missing_splits} column_mismatch={len(col_mismatch)} "
            f"in_multiple_splits={len(dup_split)}")

    # ---------------- V-11 no leakage ----------------
    key_split = defaultdict(set)
    post_split = defaultdict(set)
    for s, bucket in split_rows.items():
        for r in bucket:
            key_split[r.get("dedup_key", "")].add(s)
            post_split[(r.get("source_page", ""), r.get("post_id", ""))].add(s)
    key_leak = [k for k, v in key_split.items() if k and len(v) > 1]
    post_leak = [k for k, v in post_split.items() if len(v) > 1]
    rep.add("V-11", "no duplicate and no post straddles two splits",
            not key_leak and not post_leak,
            f"duplicate_leak={len(key_leak)} post_leak={len(post_leak)}")

    # ---------------- V-12 class balance ----------------
    n_act = sum(1 for r in rows if r.get("label") == "1")
    n_oth = sum(1 for r in rows if r.get("label") == "0")
    rate = n_act / len(rows) if rows else 0
    # The per-agency distribution is reported, not gated. The contract's §9
    # sets a >= 40 per-source-page floor as a composition target, not a V-check;
    # v1 misses it (5 of 44 agencies clear it, and 44 x 40 exceeds the corpus).
    # The data card reports the concentration so Member 5 can see it.
    per_agency = Counter(r.get("agency_id", "") for r in rows)
    thin = sorted(a for a, n in per_agency.items() if n < MIN_AGENCY_ROWS)
    ok12 = (n_act >= MIN_PER_CLASS and n_oth >= MIN_PER_CLASS
            and 0.15 <= rate <= 0.65)
    rep.add("V-12", "class balance", ok12,
            f"actionable={n_act} other={n_oth} rate={rate:.3f} "
            f"agencies={len(per_agency)} agencies_under_{MIN_AGENCY_ROWS}={len(thin)} "
            f"(reported, not gated)")

    # ---------------- V-13 token counts ----------------
    bad_tokens = [r.get("comment_id") for r in rows
                  if str(r.get("n_tokens", "")).strip() != str(len((r.get("comment_text_norm") or "").split()))]
    rep.add("V-13", "n_tokens matches the normalized text", not bad_tokens,
            f"{len(bad_tokens)} mismatches")

    # ---------------- V-14 metadata ----------------
    meta = {}
    meta_ok = False
    meta_detail = f"missing file: {args.metadata}"
    if os.path.exists(args.metadata):
        try:
            meta = json.load(io.open(args.metadata, encoding="utf-8"))
            required = ["dataset_version", "class_counts", "counts_by_split", "split_seed",
                        "lineage", "cohens_kappa", "verification_counts"]
            missing = [k for k in required if k not in meta]
            meta_ok = not missing
            meta_detail = f"missing keys: {missing}" if missing else "all required keys present"
        except Exception as e:
            meta_detail = f"parse error: {e}"
    rep.add("V-14", "metadata is complete", meta_ok, meta_detail)

    # ---------------- V-15 prior drift ----------------
    def prior(bucket):
        n = len(bucket)
        if not n:
            return None
        return sum(1 for r in bucket if r.get("label") == "1") / n

    p_tr, p_te = prior(split_rows.get("train", [])), prior(split_rows.get("test", []))
    if p_tr is None or p_te is None:
        rep.add("V-15", "test class prior within 0.10 of train", False, "missing splits")
    else:
        drift = abs(p_te - p_tr)
        rep.add("V-15", "test class prior within 0.10 of train", drift <= MAX_PRIOR_DRIFT,
                f"train={p_tr:.3f} test={p_te:.3f} drift={drift:.3f}")

    # ---------------- V-16 lineage and agency integrity ----------------
    registry = {}
    if os.path.exists(args.agencies):
        registry = {a.get("agency_id", ""): a for a in read_csv(args.agencies)}
    unknown_agency = [r.get("comment_id") for r in rows
                      if r.get("agency_id") and r.get("agency_id") not in registry]
    # agency_id is a required column (contract 5.2 col 5) and the only join to
    # the registry that holds each account's verification evidence. A row with
    # no agency_id is unattributable, so it fails here rather than passing on
    # the strength of the rows that do have one.
    missing_agency = [r.get("comment_id") for r in rows
                      if not (r.get("agency_id") or "").strip()]
    # the registry is the single source of truth for the denormalized name and
    # abbreviation; a stale copy in the dataset is a silent inconsistency
    bad_agency_name = [r.get("comment_id") for r in rows
                       if (r.get("agency_id") or "") in registry
                       and (r.get("agency") or "")
                       != (registry[r["agency_id"]].get("agency_name") or "")]
    bad_agency_abbr = [r.get("comment_id") for r in rows
                       if (r.get("agency_id") or "") in registry
                       and (r.get("agency_abbr") or "")
                       != (registry[r["agency_id"]].get("agency_abbr") or "")]
    lineage = meta.get("lineage", {}) if meta else {}
    n_raw = lineage.get("n_raw_captured", 0)
    n_cand = lineage.get("n_candidate_pool", 0)
    n_lab = lineage.get("n_labeled", 0)
    n_use = lineage.get("n_usable_final", 0)
    excl = lineage.get("n_excluded_by_reason", {}) or {}
    sum_excl = sum(excl.values()) if isinstance(excl, dict) else 0
    # Two separate branches (contract 5.6), not one chain.
    #   extraction:  raw == extracted == candidate + excluded
    #   labeling:    candidate == labeled == usable == train+dev+test
    n_split = sum(meta.get("counts_by_split", {}).values()) if meta else 0
    reconciles = (
        n_raw == n_cand + sum_excl
        and n_cand == n_lab == n_use
        and n_use == len(rows)
        and (n_split == 0 or n_split == n_use)
    )
    rep.add("V-16", "lineage reconciles and agency fields match the registry",
            not unknown_agency and not missing_agency
            and not bad_agency_name and not bad_agency_abbr and reconciles,
            f"missing_agency={len(missing_agency)} unknown_agency={len(unknown_agency)} "
            f"agency_name_mismatch={len(bad_agency_name)} "
            f"agency_abbr_mismatch={len(bad_agency_abbr)} "
            f"raw={n_raw} candidate={n_cand} excluded={sum_excl} labeled={n_lab} "
            f"usable={n_use} rows={len(rows)} split_total={n_split} reconciles={reconciles}")

    # ---------------- V-17 annotation completeness ----------------
    bad_ver = [r for r in rows if r.get("verification") not in VERIFICATIONS]
    verified = sum(1 for r in rows
                   if r.get("verification") in
                   ("llm_verified", "human_verified", "human_labeled"))
    n_l2 = sum(1 for r in rows if r.get("label_2") not in ("", None))
    need_l2 = math.ceil(len(rows) * MIN_RELABEL_RATE)
    kappa = meta.get("cohens_kappa") if meta else None
    method = ((meta.get("verification_method") or "").strip() if meta else "")
    ok17 = (not bad_ver and verified >= MIN_VERIFIED
            and n_l2 >= need_l2
            and isinstance(kappa, (int, float)) and kappa >= MIN_KAPPA
            and bool(method))
    rep.add("V-17", "annotation completeness, verification and reliability",
            ok17,
            f"bad_verification={len(bad_ver)} verified={verified} "
            f"(need >= {MIN_VERIFIED}) relabeled={n_l2}/{len(rows)} "
            f"(need >= {need_l2}) kappa={kappa} (need >= {MIN_KAPPA}) "
            f"method={method!r}")

    # ---------------- output ----------------
    text = rep.render()
    print(text)

    if args.report:
        os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
        with io.open(args.report, "w", encoding="utf-8", newline="") as fh:
            fh.write(text + "\n")
        print(f"report -> {args.report}")

    return 1 if rep.errors else 0


if __name__ == "__main__":
    sys.exit(main())
