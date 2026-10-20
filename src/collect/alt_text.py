"""
alt_text.py — strip generated image descriptions out of captured comments.

Facebook exposes a sticker or photo comment's accessible description as if
it were the comment text:

    Hey Buddy A blue gradient human figure with eyes moving left and right, ...

The comment is "Hey Buddy"; the rest is the alt text of a sticker. The same
happens for a shared photo and for a link preview.

The alt text is recognisable: it is long, and it is dense with visual and
spatial vocabulary that a citizen's sentence would not contain. The trim
only fires when both are true, so an ordinary long comment is left alone.
"""

from __future__ import annotations

import re

# Vocabulary that only shows up in generated image descriptions
VISUAL_WORDS = {
    "gradient", "background", "pointing", "pointed", "symbol", "icon", "image",
    "photo", "picture", "graphic", "illustration", "screenshot", "avatar",
    "sticker", "moodies", "human figure", "index finger", "curling", "sparkles",
    "silhouette", "rendered", "text reads", "saying", "appears to be",
    "left hand", "right hand", "eyes moving", "hair", "wearing", "holding",
    "shirt", "jacket", "colorful", "blurry", "close-up", "close up",
    "colored", "colourful", "floating", "against", "gives a", "thumbs up",
    "girl giving", "boy giving", "womans face", "mans face", "smiling",
    "standing", "sitting", "holding a", "looking at", "with a",
}

MIN_ALT_LEN = 45
MIN_ALT_HITS = 2


def clean_alt_text(text: str) -> str:
    """Trim a trailing alt-text description off a comment."""
    if not text or len(text) < MIN_ALT_LEN:
        return text

    words = text.split()
    for i in range(2, len(words) - 2):
        window = " ".join(words[i:i + 8]).lower()
        hits = sum(1 for w in VISUAL_WORDS if w in window)
        if hits >= MIN_ALT_HITS:
            candidate = " ".join(words[:i]).strip(" .,!-")
            if candidate and len(candidate) >= 3:
                return candidate
    return text


def clean_comment(text: str) -> str:
    """The full clean for one captured comment."""
    t = (text or "").strip()
    if not t:
        return ""
    t = re.sub(r"\s+", " ", t)
    return clean_alt_text(t)
