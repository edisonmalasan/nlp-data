# Platform coverage — what was collected, and what was not

This file records the source-frame decisions and the reasons behind them, so the
Methodology section can be written from evidence rather than memory. The binding
requirements are in `DATA_CONTRACT.md` §3.1 (source eligibility) and §3.2 (platform
scope).

---

## 1. The source frame

The frame is **systematic, not hand-picked**: every Philippine national department, plus
the bureaus, commissions and government corporations that publish on social media.

Two things follow from that, and both matter for how the paper describes the corpus.

**The high-traffic accounts are in the frame by construction.** The accounts that draw
the most comments — DPWH, DOH, DSWD, DepEd, DTI — are the big ones, and a systematic
frame includes them. No account was selected *because* it was controversial or because
its posts went viral.

**Virality is a property of the data, not a selection criterion.** The post window is
"the most recent N posts" on each account, and the window is the same for every
account. A post that happened to go viral is captured if it was recent, and its
comment volume is recorded. Selecting posts *because* they were viral would be
selecting on the outcome, and any performance claim would then be a claim about
corruption outrage rather than about citizen suggestions to government.

### How the accounts were identified

Guessing a Facebook slug does not work. `PSAofficial` resolves to a page called
"Pet Society", and roughly a third of the guesses resolve to nothing at all. So:

| Step | How | Evidence |
|---|---|---|
| 1 | Each agency's **own website** is read for the Facebook page it links to | `data/provenance/website_discovery.json` |
| 2 | The page is loaded and its **name is checked against the agency** | `data/provenance/source_verification.json` |
| 3 | Each agency's **Facebook contact-info block** is read for its other official accounts (X, YouTube) | `data/provenance/official_links.json` |

The verification is on the **rendered page**, not `document.title`: a Facebook profile's
title stays `(N) Facebook` and the agency's name is in the body. The check is against
the page's *identity block* — its name and follower count — and not the whole body,
because a token that appears further down the page, in the navigation, is not evidence
of anything. Two accounts were rejected by the tighter check: a page called
"Happiness Travels and Tours" had been accepted for the Department of Tourism, and
`nsc.gov.ph` for the National Security Council.

---

## 2. Platform coverage

| Platform | Accounts | Yield | Role |
|---|---|---|---|
| **Facebook** | 32 | primary | **Primary.** `dataset_v1.csv`. Matches the paper title and abstract exactly. |
| **YouTube** | 10 | secondary | `dataset_v1_ext.csv`. Highest comment volume of the four, narrowest vocabulary. |
| **X** | 5 | optional | `dataset_v1_ext.csv`. Least accessible of the four. |
| **Reddit** | **0** | — | **Contributes nothing.** See below. |

### Reddit: no eligible source exists

The contract treats Reddit as optional and expects it to be sparse (§3.2: *"Government-
specific threads are sparse"*). The collection confirms it, and goes further.

A Reddit search for every agency's name returned **88 candidate subreddits**. Only
**one** is even about government: `r/PHGov`, whose own description reads *"Community
dedicated towards the Philippine Government"*.

It is **not** an official account. It was created by a user, and it fails the
contract's own eligibility criteria:

- **S1** — it is not the official account of a national government agency;
- **S2** — it is a community, not a verified or official account.

The remaining 87 candidates are general-interest communities (`r/Philippines`,
`r/MilitaryPorn`, `r/NewsOfTheWeird`, `r/Teachers`, `r/weather`, …). They are not
government accounts and were not collected.

**Decision: Reddit contributes zero comments, and this is a finding, not a gap.** The
reason is recorded here so the write-up states it as a methodological fact: *no
Philippine national government agency operates a subreddit.* Including a community
subreddit would have meant either breaking S1/S2 or quietly changing the sampling
frame, and neither is a decision the collector should make on its own.

### X: five accounts, from the agencies' own declarations

The five X accounts were not guessed. They were read from each agency's Facebook
contact-info block, so they are the handles the agencies declare for themselves:
DOST-PAGASA, DSWD, DPWH, DILG, DTI. The other five agencies declare no X account.
This is the "least accessible of the four" the contract describes, and it shows in
the yield.

---

## 3. The two sampling strata

The pilot falsified the working assumption that recent posts are request-bearing.
Recent posts turned out to be dominated by announcements — typhoon bulletins and
programme notices — where citizens react rather than ask. The request-marker rate on
that stratum was **14%**, below the contract's 15–65% band, which triggered the
pre-registered fallback in §3.4.

| Stratum | What it is | `stratum` value |
|---|---|---|
| **A** | The most recent N posts on each account | `recent` |
| **B** | Posts whose text contains an invitation marker | `invites` |

Stratum B is an **addition**, not a replacement. Nothing collected under stratum A is
discarded, and the `stratum` column records which is which, so the two can be
analysed separately and reported separately.

> **The invitation-marker patterns are the collector's choice, not the contract's.**
> The contract pre-registered the *remedy* ("sample additional posts known to solicit
> citizen input"), but the specific marker list is a methodological decision about
> what counts as a request-inviting post. **It needs the adviser's sign-off before it
> goes in the paper.** The marker list is in `src/collect/find_invites.js`.

---

## 4. Collection method

DOM collection through Orca's built-in browser, using the session the researcher is
already signed into. No API key, no access token, no copy of the browser profile, and
no focus stolen from the researcher's screen.

The browser drives **one tab at a time per worker**, and several workers run at once —
one per platform, each on its own tab. `goto` and `eval` take an explicit page id, so a
worker that stays on its own tab does not disturb another worker.

Three faults were found and fixed during collection, each of which had silently
emptied an account:

1. **A post permalink does not reliably render its thread.** For a logged-in session
   Facebook serves the post without its comments, or the home feed instead. Clicking
   the permalink on the account's own page opens the post with the thread attached, so
   the collector clicks the posts where they sit.
2. **A photo post's permalink is a preview.** It says *"This photo is from a post"*,
   shows an empty comment box, and carries a *"View post"* link to the post, where the
   thread is. Many agencies post almost nothing but photos, and their feed has no
   `/posts/` links at all — the first matcher only accepted `/posts/`, so those pages
   had no permalinks.
3. **A snapshot with no comments counted as a collected account.** An account whose
   first attempt came back empty was never retried.

The feed was also being scrolled with the comment-thread scroller, which an account
page does not have, so the feed never grew and only the posts that happened to render
were ever seen.

---

## 5. What the numbers are

The authoritative figures are in `data/provenance/dataset_report.json`, regenerated by
`tools/dataset_report.py` on every clean. The per-account collection log is
`data/provenance/collection_log.csv`, and the per-worker logs are in
`data/provenance/logs/`.
