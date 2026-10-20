"""
normalize.py — text normalization for the dataset.

Implements DATA_CONTRACT.md 6.2 (L0 -> L1), 6.3 (post context assembly) and
6.6 (dedup key). The rules are applied in the exact order the contract
specifies, because the order is load-bearing: the URL rule must run before the
digit rule, or a phone number inside a URL gets replaced as a number.

Design rules:
  * Casing, punctuation and emoji are PRESERVED in the shipped normalized text.
    Lowercasing destroys the sentence-initial "Please" distinction for no
    benefit, and the feature regexes are specified case-insensitively.
  * Nothing here is destructive. The L0 verbatim text is always kept alongside.
  * Empty results are the empty string, never None.
"""

from __future__ import annotations

import re
import unicodedata

# --- character classes ------------------------------------------------------

# Zero-width and bidi control characters (contract 6.2 step 2)
ZERO_WIDTH = re.compile(
    "[\u200B-\u200F\u202A-\u202E\u2060\uFEFF]"
)

# URL (contract 6.2 step 3)
URL_RE = re.compile(
    r"(?:https?://|www\.)[^\s<>\"']+"
    r"|\b[\w.-]+\.(?:com|ph|net|org|gov|edu|io|co)(?:/[^\s<>\"']*)?",
    re.IGNORECASE,
)

# @mention (contract 6.2 step 4)
MENTION_RE = re.compile(r"@[\w.$-]+")

# Email (contract 6.2 step 6)
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")

# Phone-like: 7+ digits with optional separators, plus common PH prefixes
PHONE_RE = re.compile(
    r"(?<!\w)(?:\+?63|0)\d[\d\s\-().]{5,}\d(?!\w)"
)

# Digit run of 4 or more (contract 6.2 step 7)
LONG_DIGITS_RE = re.compile(r"\d{4,}")

# Whitespace
WS_RE = re.compile(r"\s+")

# Non-alphanumeric for the dedup key (contract 6.6)
NON_ALNUM_RE = re.compile(r"[^0-9a-z]+")

# Segment markers for context assembly (contract 6.3)
POST_MARK = "[POST]"
PARENT_MARK = "[COMMENT_PARENT]"


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------


def normalize_text(text: str) -> str:
    """L0 -> L1. The contract's nine steps, in order."""
    if not text:
        return ""

    # 1. NFC
    text = unicodedata.normalize("NFC", text)

    # 2. zero-width and bidi controls
    text = ZERO_WIDTH.sub("", text)

    # 3. email -> <EMAIL>   (MUST precede URL and mention, contract 6.2)
    text = EMAIL_RE.sub("<EMAIL>", text)

    # 4. URLs -> <URL>
    text = URL_RE.sub("<URL>", text)

    # 5. @mentions -> <USER>
    text = MENTION_RE.sub("<USER>", text)

    # 6. phone -> <PHONE>
    text = PHONE_RE.sub("<PHONE>", text)

    # 7. digit runs of 4+ -> <NUM>
    text = LONG_DIGITS_RE.sub("<NUM>", text)

    # 8. collapse whitespace and strip
    text = WS_RE.sub(" ", text).strip()

    # 9. casing, punctuation and emoji are deliberately preserved
    return text


def dedup_key(text: str) -> str:
    """Contract 6.6. Lowercase, strip all non-alphanumerics, collapse spaces."""
    if not text:
        return ""
    key = unicodedata.normalize("NFC", text).lower()
    key = NON_ALNUM_RE.sub(" ", key)
    return WS_RE.sub(" ", key).strip()


def build_context(post_text: str = "", parent_comment_text: str = "") -> str:
    """Contract 6.3. Assemble the post + parent context.

    Empty segments are dropped entirely, not left as empty brackets.
    """
    parts = []
    post_n = normalize_text(post_text or "")
    parent_n = normalize_text(parent_comment_text or "")

    if post_n:
        parts.append(f"{POST_MARK} {post_n}")
    if parent_n:
        parts.append(f"{PARENT_MARK} {parent_n}")

    return " ".join(parts)


def token_count(text: str) -> int:
    """Whitespace token count of the normalized text (contract 5.2, column 21)."""
    if not text:
        return 0
    return len(text.split())


def token_set(text: str) -> set:
    """Token set for near-duplicate detection (contract 7.2)."""
    return set(text.lower().split())
