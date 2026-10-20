"""
pii.py — anonymization of the comment text.

Implements DATA_CONTRACT.md 11. Names, handles, phone numbers, emails and
ID-like digit runs are replaced with placeholders in the L1 normalized text.

The rule that matters: the L0 verbatim text is never edited. The scrub only
produces the L1 text, and `pii_redacted` records whether a row was touched.

What is deliberately NOT done:
  * no attempt to identify anyone
  * no cross-referencing against any other data source
  * no removal of a row for containing personal data unless the row is
    dominated by it (that is X_PII, handled by the caller)
"""

from __future__ import annotations

import re

REASON = "X_PII"

# --- name-like patterns ----------------------------------------------------
# Deliberately conservative. A false positive here turns a Filipino comment
# into word salad, so the patterns require a capitalised word next to a
# kinship or honorific term, or an explicit introduction.

HONORIFICS = [
    "Mr", "Mrs", "Ms", "Mister", "Ma'am", "Mam", "Sir", "Madam",
    "Dr", "Engr", "Atty", "Hon", "Governor", "Mayor", "President",
]

NAME_AFTER_HONORIFIC_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(h) for h in HONORIFICS) + r")\.?\s+"
    r"(?:[A-Z][a-z]+\s+){0,2}[A-Z][a-z]+\b"
)

SIR_MADAM_RE = re.compile(
    r"\b(?:si\s+[A-Z][a-z]+|kung\s+si\s+[A-Z][a-z]+|"
    r"Mr\.?\s*[A-Z][a-z]+|Mrs\.?\s*[A-Z][a-z]+|Ms\.?\s*[A-Z][a-z]+)\b"
)

# A name introduced as a person: "ni Juan", "si Maria", "kay Ana"
NATIVE_NAME_RE = re.compile(
    r"\b(?:ni|si|kay|niya|nila)\s+[A-Z][a-z]{2,}\b"
)

# --- contact details --------------------------------------------------------

PHONE_RE = re.compile(
    r"(?<!\w)(?:\+?63|0)\d[\d\s\-().]{5,}\d(?!\w)"
)
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
URL_RE = re.compile(r"(?:https?://|www\.)[^\s<>\"']+")
MENTION_RE = re.compile(r"@[\w.$-]+")

# --- government / personal id numbers ---------------------------------------

LONG_DIGITS_RE = re.compile(r"\d{4,}")

# --- address-like -----------------------------------------------------------

ADDRESS_RE = re.compile(
    r"\b\d{1,4}\s+[A-Z][a-z]+\s+(?:Street|St\.|Avenue|Ave\.|Road|Rd\.|"
    r"Barangay|Blk\.|Block|Floor|Fl\.|Phase|Puro| sitio)\b",
    re.IGNORECASE,
)

# --- plate numbers ----------------------------------------------------------

PLATE_RE = re.compile(r"\b[A-Z]{3}\s?\d{3}\s?[A-Z]{1,2}\b")

# Placeholders used in the L1 text
P_USER = "<USER>"
P_PHONE = "<PHONE>"
P_EMAIL = "<EMAIL>"
P_URL = "<URL>"
P_NUM = "<NUM>"
P_NAME = "<NAME>"


def scrub_text(text: str) -> tuple:
    """Return (scrubbed_text, was_modified, hits)."""
    if not text:
        return "", False, []

    hits = []
    out = text

    def sub(pattern, repl, label):
        nonlocal out
        out, n = pattern.subn(repl, out)
        if n:
            hits.append(f"{label}x{n}")
        return n

    # order matters: URLs before digits, email before the generic digit rule
    sub(EMAIL_RE, P_EMAIL, "email")
    sub(URL_RE, P_URL, "url")
    sub(MENTION_RE, P_USER, "mention")
    sub(PHONE_RE, P_PHONE, "phone")
    sub(ADDRESS_RE, lambda m: re.sub(r"\d+", P_NUM, m.group(0)), "address")
    sub(PLATE_RE, P_NUM, "plate")
    sub(NAME_AFTER_HONORIFIC_RE, P_NAME, "name")
    sub(SIR_MADAM_RE, P_NAME, "name")
    sub(NATIVE_NAME_RE, lambda m: m.group(0).split(" ")[0] + " " + P_NAME, "name")
    sub(LONG_DIGITS_RE, P_NUM, "digits")

    return out, bool(hits), hits


def dominates(text: str, hits: list) -> bool:
    """Is the row mostly personal data? Then it is X_PII and gets removed
    rather than scrubbed (contract 4.2, reason code X_PII)."""
    if not text:
        return False
    words = text.split()
    if not words:
        return False
    # three or more distinct kinds of personal data in one short comment
    kinds = {h.rstrip("0123456789") for h in hits}
    return len(kinds) >= 3 and len(words) < 12


def scrub_rows(rows: list, text_field: str = "comment_text_norm") -> tuple:
    """Scrub a list of rows. Returns (kept, removed).

    Kept rows get `pii_redacted` set. Removed rows are X_PII and carry a
    `_reason`.
    """
    kept = []
    removed = []
    for row in rows:
        text = row.get(text_field) or ""
        if not text:
            kept.append(row)
            continue
        scrubbed, modified, hits = scrub_text(text)
        if dominates(text, hits):
            dup = dict(row)
            dup["_reason"] = REASON
            dup["_rule"] = "pii_dominant"
            removed.append(dup)
            continue
        new_row = dict(row)
        if modified:
            new_row[text_field] = scrubbed
            new_row["pii_redacted"] = "true"
        else:
            new_row["pii_redacted"] = "false"
        kept.append(new_row)
    return kept, removed
