"""
spam.py — spam, low-value and automated-content filters.

Implements DATA_CONTRACT.md 8. Rules F1-F8.

  F1-F6  automatic, deterministic
  F7-F8  manual review by the collector, logged per row

The most important rule in this file is the one that is NOT a filter:
never remove a row for its sentiment, profanity, political content, or length
(beyond empty text). Aggressive "quality" filtering is the fastest way to
silently lose the negative and non-actionable classes and wreck the class
balance the paper reports.

Every removed row leaves with a `_reason` of X_SPAM so the exclusion ledger
reconciles.
"""

from __future__ import annotations

import re
from collections import defaultdict

from .dedup import jaccard
from .normalize import token_set

REASON = "X_SPAM"

# --- F1 / F3: promotional and commercial markers ----------------------------

PROMO_TERMS = [
    "job", "hiring", "promo code", "discount", "click here", "dm me", "sale",
    "investment", "crypto", "mlm", "loan", "online business", "shopee", "lazada",
    "telegram", "earn money", "work from home", "sideline", "reseller", "live selling",
    "part time", "part-time", "income", "affiliate", "giveaway", "raffle",
    "voucher", "free shipping", "cashback", "giveaways",
]

SHORTENERS_RE = re.compile(
    r"https?://(?:bit\.ly|tinyurl\.com|t\.me|is\.gd|shorturl\.at|cutt\.ly|rebrand\.ly|lnkd\.in)",
    re.IGNORECASE,
)

REGISTRATION_RE = re.compile(
    r"(?:add\s+me\s+on\s+fb|gcash|codash|opengov|"
    r"\bwhatsapp\s+(?:me|\+\d)|"
    r"\bme\s+s\s+[:：]\s*\+?\d)",
    re.IGNORECASE,
)

ACCOUNT_BURST_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)

# --- F4: repeated-character padding ----------------------------------------

REPEAT_CHAR_RE = re.compile(r"(.)\1{5,}")

REPEATED_TOKEN_RE = re.compile(r"^\s*(\w+)(?:\s+\1){2,}\s*$", re.IGNORECASE)

# Real Filipino words that happen to look like a repeated unit. Exempted so
# "mama" is not deleted as padding.
_REPEAT_ALLOWLIST = {
    "mama", "papa", "nana", "lola", "lolo", "dada", "tata", "kaka", "tita",
    "tito", "manong", "manang",
}


def is_repeated_token(text: str) -> bool:
    """Contract 8, F4: the text is a single repeated token.

    Covers `aaaaaaaaaaaaaaaa`, `hahaha` and `HAHA`. The unit may be 1-4
    characters and must repeat at least twice. Short real words that look
    repeated are exempt.
    """
    words = text.strip().split()
    if len(words) != 1:
        return False
    w = words[0]
    if len(w) < 4 or not w.isalnum():
        return False
    if w.lower() in _REPEAT_ALLOWLIST:
        return False
    for unit_len in range(1, 5):
        if len(w) % unit_len:
            continue
        unit = w[:unit_len]
        repeats = len(w) // unit_len
        if repeats < 2:
            continue
        if w == unit * repeats:
            return True
    return False

# --- F2: same URL three or more times from one account ----------------------

URL_RE = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)

# --- emoji-only padding (F5) ------------------------------------------------

EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF☀-➿]"
)


def _has_word(text: str, words: list) -> list:
    low = text.lower()
    return [w for w in words if w in low]


def scan_text(row: dict) -> str:
    """The text the link-related rules inspect.

    Normalization has already replaced URLs with `<URL>`, mentions with
    `<USER>` and so on, so a rule looking for a live link would never fire
    on the normalized text alone. These rules therefore scan the normalized
    text AND the verbatim text together.

    Only detection uses this. Nothing from it is written to the dataset.
    """
    norm = row.get("comment_text_norm") or row.get("comment_text") or ""
    raw = row.get("comment_text") or ""
    if raw and raw != norm:
        return f"{norm} {raw}"
    return norm


def normalized_text(row: dict) -> str:
    """The text the structural rules inspect (padding, emoji-only)."""
    return row.get("comment_text_norm") or row.get("comment_text") or ""


def rule_f1_promo_with_link(text: str) -> bool:
    """Promotional markers together with a link."""
    return bool(_has_word(text, PROMO_TERMS)) and bool(URL_RE.search(text))


def rule_f3_commercial(text: str) -> bool:
    """Shortener or registration regex."""
    return bool(SHORTENERS_RE.search(text) or REGISTRATION_RE.search(text))


def rule_f4_padding(text: str) -> bool:
    """Repeated characters or a repeated token."""
    if REPEAT_CHAR_RE.search(text):
        return True
    if REPEATED_TOKEN_RE.match(text.strip()):
        return True
    if is_repeated_token(text):
        return True
    return False


def rule_f5_emoji_padding(text: str) -> bool:
    """Emoji with no word token left."""
    stripped = EMOJI_RE.sub("", text)
    stripped = re.sub(r"[^\w\s]", " ", stripped)
    return not stripped.split()


def rule_f2_url_burst(text: str, account_urls: dict) -> bool:
    """F2: the same URL seen at least 3 times from one account.

    `account_urls` maps an account key to the set of URLs that account has
    posted. The caller owns that state across the whole pool.
    """
    for url in URL_RE.findall(text):
        if len(account_urls.get(url, set())) >= 3:
            return True
    return False


def rule_f6_account_burst(text: str, account_texts: dict, threshold: float = 0.85) -> bool:
    """F6: an account posting near-identical text repeatedly.

    `account_texts` maps an account key to the list of token sets that account
    has already posted in this pool.
    """
    from .dedup import jaccard
    from .normalize import token_set

    mine = token_set(text)
    if not mine:
        return False
    for other in account_texts:
        if jaccard(mine, other) >= threshold:
            return True
    return False


def filter_spam(rows: list, account_key: str = "source_page",
                 post_key: str = "post_id") -> tuple:
    """Apply F1-F6 across the pool.

    F2 and F6 are corpus-level rules, so they need state across the whole pool;
    they are applied on a second pass once the per-row rules have run.
    """
    kept = []
    removed = []

    # ---- pass 1: per-row rules ----
    survivors = []
    for row in rows:
        norm = normalized_text(row)
        scan = scan_text(row)
        reason = None
        if rule_f5_emoji_padding(norm):
            reason = "F5_emoji_padding"
        elif rule_f4_padding(norm):
            reason = "F4_padding"
        elif rule_f3_commercial(scan):
            reason = "F3_commercial"
        elif rule_f1_promo_with_link(scan):
            reason = "F1_promo_with_link"

        if reason:
            dup = dict(row)
            dup["_reason"] = REASON
            dup["_rule"] = reason
            removed.append(dup)
        else:
            survivors.append(row)

    # ---- pass 2: corpus-level rules ----
    account_urls = defaultdict(set)
    account_texts = defaultdict(list)
    from .normalize import token_set

    url_counter = defaultdict(int)
    for url, accts in account_urls.items():
        url_counter[url] = len(accts)

    url_by_account = defaultdict(set)
    for row in survivors:
        text = scan_text(row)
        acct = (row.get(account_key, ""), row.get(post_key, ""))
        for url in URL_RE.findall(text):
            url_by_account[(acct, url)].add(url)

    # F2 needs the same url from 3+ comments of the SAME account
    per_account_url = defaultdict(set)
    for row in survivors:
        text = scan_text(row)
        acct = row.get(account_key, "")
        for url in URL_RE.findall(text):
            per_account_url[(acct, url)].add(row.get("comment_id", ""))

    for row in survivors:
        text = scan_text(row)
        acct = row.get(account_key, "")
        reason = None

        for url in URL_RE.findall(text):
            if len(per_account_url.get((acct, url), ())) >= 3:
                reason = "F2_url_burst"
                break

        if reason is None:
            # F6 compares against PREVIOUS rows only. Comparing against the
            # row itself would give a Jaccard of 1.0 and delete every row.
            seen = account_texts.get((acct, row.get(post_key, "")), [])
            mine = token_set(text)
            if mine:
                for other in seen:
                    if other and jaccard(mine, other) >= 0.85:
                        reason = "F6_account_burst"
                        break

        if reason:
            dup = dict(row)
            dup["_reason"] = REASON
            dup["_rule"] = reason
            removed.append(dup)
        else:
            kept.append(row)
            # record this row for the NEXT row's F6 comparison
            acct = (row.get(account_key, ""), row.get(post_key, ""))
            account_texts[acct].append(token_set(text))

    return kept, removed
