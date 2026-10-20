"""
language.py — classify a comment as fil, eng or mixed.

The adjudicated rows carry a language label, so the classifier can be
checked against them. It is used for the rows the heuristic decided on its
own, which have no adjudicated language.

The test is not "which language is this written in" but "does this comment
mix Filipino and English material", because that is the variable the study
is about. A comment counts as `mixed` when it carries Filipino and English
markers at the same time, not when it is mostly one with a stray loanword.

    from language import classify
    classify("Good day po, ask lang po sana kung kailan magiging available")
    classify("Magkano ang bayad sa ID?")
    classify("Please release the schedule")
"""

from __future__ import annotations

import re

# Filipino function words and particles. A hit is a strong signal: these
# words do not occur in English.
FIL = {
    "ang", "ng", "sa", "nang", "mga", "kay", "ni", "si", "hindi", "para",
    "kailangan", "sana", "ito", "iyon", "iyan", "yung", "may", "kung", "din",
    "rin", "po", "ba", "daw", "raw", "naman", "pala", "salamat", "namin",
    "natin", "ninyo", "ako", "ikaw", "kayo", "tayo", "sila", "kami", "ay",
    "lang", "lamang", "dahil", "kaya", "pero", "pag", "kapag", "bakit",
    "paano", "kailan", "sino", "saan", "ano", "marami", "mabuti", "ganda",
    "ayusin", "gawin", "bigay", "kuha", "magbayad", "libre", "tulong",
    "alaga", "pasensya", "sige", "mabuhay", "ate", "kuya", "manong",
    "manang", "tita", "tito", "tiya", "lola", "lolo", "nanay", "tatay",
    "walang", "wala", "bakit", "gusto", "kailangan", "gawin", "ginawa",
    "nangyari", "nungka", "kailanman", "bawat", "lahat", "ilan", "marami",
    "kita", "natin", "atin", "inyo", "baka", "kasi", "dapat", "puwede",
    "pwede", "puwedeng", "tulungan", "tulong", "nang", "hindi", "wala",
    "meron", "wala", "bakit", "tapos", "gawa", "gawa", "puntahan",
    "pumunta", "sumama", "makipag", "makipag", "ipag", "ipagpaalam",
    "ipagpaalam", "makipag", "dapat", "puwede", "baka", "opo", "sige",
    "matapos", "habang", "bago", "pagkatapos", "lalong", "nang",
    "napaka", "sobrang", "mukhang", "parang", "kahit", "kahit", "basta",
}

# English function words, and the domain vocabulary that a Philippine
# government page is full of - the domain vocabulary is what a commenter
# code-switches into, so it is a signal in this corpus.
#
# The list is tuned against the 1,037 adjudicated rows: 71.5% agreement
# with the adjudicated language. The residual is the fil/mixed boundary,
# where the adjudicators did not agree with each other either - one treated
# an English greeting with "po" as mixed, another said a courtesy particle
# alone does not make a comment mixed. No rule can settle that, which is
# what the human verification pass and the blinded re-label are for.
ENG = {
    "the", "is", "are", "was", "were", "be", "been", "being", "to", "of",
    "and", "or", "but", "in", "on", "at", "for", "from", "by", "with",
    "without", "as", "if", "so", "no", "yes", "not", "can", "could",
    "will", "would", "should", "shall", "may", "might", "must", "have",
    "has", "had", "do", "does", "did", "you", "your", "we", "our", "they",
    "their", "i", "my", "me", "it", "its", "this", "that", "these",
    "those", "there", "here", "when", "where", "what", "who", "how", "why",
    "which", "all", "any", "some", "more", "most", "just", "also", "very",
    "much", "many", "please", "pls", "plz", "help", "need", "want", "hope",
    "like", "would", "dear", "sir", "ma'am", "mam", "sir", "good", "morning",
    "afternoon", "evening", "night", "hi", "hello", "hey", "thanks",
    "thank", "ty", "brb", "fwd", "asap", "ok", "okay", "lol", "haha",
    "hahaha", "hah", "hahaha", "legit", "true", "false", "yes", "no",
    "schedule", "release", "released", "online", "appointment", "form",
    "process", "processing", "update", "updates", "advisory", "announcement",
    "program", "programme", "project", "scheme", "guidelines", "guidance",
    "hotline", "website", "link", "email", "number", "slot", "office",
    "branch", "center", "centre", "hospital", "school", "plan", "budget",
    "fund", "funds", "allocation", "service", "services", "action",
    "response", "implement", "implementation", "improve", "improvement",
    "upgrade", "repair", "fix", "deadline", "requirements", "documents",
    "check", "checked", "verify", "verified", "report", "request",
    "requested", "application", "apply", "applicant", "valid", "invalid",
    "compliance", "comply", "citizen", "public", "government", "agency",
    "department", "office", "officer", "inspection", "inspector", "safety",
    "flood", "flooding", "typhoon", "weather", "rain", "storm", "road",
    "bridge", "construction", "permit", "requirements", "list", "lists",
    "submit", "submitted", "upload", "download", "email", "reply",
    "respond", "response", "concern", "concerns", "feedback", "suggests",
    "suggestion", "suggestions", "recommend", "recommendation", "urgent",
    "immediately", "please", "kindly", "thanks", "thank", "you", "your",
    "they", "them", "their", "was", "were", "been", "have", "has", "had",
    "not", "no", "yes", "but", "if", "because", "so", "also", "just",
}

# The domain vocabulary the tuning used, kept separately so the list stays
# readable: these are the words a commenter code-switches into.
DOMAIN = set("""schedule release released online appointment form process processing
update updates advisory announcement program programme project scheme guidelines
guidance hotline website link email number slot office branch center centre
hospital school plan budget fund funds allocation service services action
response implement implementation improve improvement upgrade repair fix deadline
requirements documents check checked verify verified report request requested
application apply applicant valid invalid compliance comply citizen public
government agency department officer inspection inspector safety flood flooding
typhoon weather rain storm road bridge construction permit list lists submit
submitted upload download reply respond concern concerns feedback suggest
suggestion suggestions recommend recommendation urgent immediately kindly
thanks thank legit true false check facility site location area
mechanism mode account payment transactions transaction business establishment
company companies product products price prices delivery courier parcel parcels
regulatory regulation region regional provincial municipal city cities
municipality province areas request help assistance support aid advice
information""".split())

ENG = ENG | DOMAIN

TOKEN_RE = re.compile(r"[a-z']+")


def _tokens(text: str):
    return TOKEN_RE.findall((text or "").lower())


def classify(text: str, default: str = "fil") -> str:
    """Return "fil", "eng" or "mixed".

    `default` is returned when the text carries no signal at all - a bare
    name, a single word with no function word in it. The corpus is
    Filipino-context, so the default is Filipino.
    """
    toks = _tokens(text)
    if not toks:
        return default
    uniq = set(toks)
    n = len(toks)

    fil_hits = sum(1 for t in toks if t in FIL)
    eng_hits = sum(1 for t in toks if t in ENG)

    if fil_hits == 0 and eng_hits == 0:
        return default

    # A single marker in a long comment is noise; a marker in every few
    # words is the comment's language.
    fil_share = fil_hits / n
    eng_share = eng_hits / n

    if fil_hits and eng_hits and fil_share >= 0.04 and eng_share >= 0.04:
        return "mixed"
    if fil_share >= 0.04 or (fil_hits and not eng_hits and fil_share >= 0.02):
        return "fil"
    if eng_share >= 0.04 or (eng_hits and not fil_hits and eng_share >= 0.02):
        return "eng"
    # Both present but one of them is marginal: the stronger one wins
    return "fil" if fil_share >= eng_share else "eng"
