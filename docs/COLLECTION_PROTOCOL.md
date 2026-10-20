# COLLECTION_PROTOCOL.md

**How comments get collected.** Read this before the first scrape.

- Contract: `DATA_CONTRACT.md` §3 (sources and collection), §4 (inclusion/exclusion)
- Source registry: `data/provenance/government_agencies.csv`
- Run log: `data/provenance/collection_log.csv`
- Raw snapshots: `data/raw/<platform>/<source_page>/<run_id>.json`

---

## 1. The method

Collection runs in **your own Chrome**, already signed in to Facebook, X, YouTube and
Reddit. A computer-use agent (orca) drives the visible browser, reads the rendered DOM of
each post, and writes a **raw snapshot**. A script then turns the snapshot into the
interim files the cleaning pipeline consumes.

```
your Chrome (signed in)
   │  src/collect/orca_fb.py drives it via orca computer-use,
   │  reads the accessibility tree
   ▼
data/raw/<platform>/<source_page>/<run_id>.json      ← raw snapshot, immutable
   │  python src/collect/to_interim.py
   ▼
data/interim/comments_captured.csv                  ← verbatim, pre-cleaning
data/interim/posts_captured.csv
   │  python src/clean/pipeline.py
   ▼
data/processed/candidate_pool.csv                   ← cleaned
```

### The tool

`src/collect/orca_fb.py` is the collector. It drives the browser through
`orca computer` and reads the **accessibility tree**, not the HTML DOM. Two things it
gets right that a naive script does not:

- **Navigation is verified.** Facebook is an SPA and swallows failed navigations
  silently, so the address bar holding a URL is not evidence anything happened. The
  check is on the loaded document URL, and the sequence that works is
  `Ctrl+L → set-value → Delete → Return` (`paste-text` lets the omnibox
  inline-autocomplete to a different, shorter URL).
- **The thread is loaded to the end.** A post's comment list grows lazily and
  slowly. Stopping when the count holds still for a few scrolls catches the first
  ten comments and calls it the whole thread. The scroll loop keeps going until
  the count has been stable for several rounds *and* a floor of scroll actions has
  passed.

The window must be focused for keyboard input. The tool uses `--restore-window` to
bring Chrome forward itself, but it will steal focus from whatever you are doing.

**Nothing is filtered during collection.** Every comment is captured verbatim. Filtering
happens later, in one place, with a reason code for every removal.

### Why an authenticated session

Reading the DOM in a signed-in session shows what a real signed-in visitor sees, which
includes the full comment thread and any replies. That is a **sampling** fact worth
stating in the paper: the dataset covers the comments visible to the collection session.
For public government pages this is effectively the public thread.

**What is never collected:** the commenter's profile page, their friend list, their other
activity, or any identifier that is not the comment text itself. The display name is
captured only so the pipeline can spot agency-authored comments (`X_OFFICIAL`); it is
stripped before anything is published.

---

## 2. Before you start

- [ ] `data/provenance/government_agencies.csv` has at least one row per agency you
      intend to collect from, with `official_verified = true` and all six
      `eligibility_s*` set to `true`.
- [ ] Chrome is open and signed in to the platform you are collecting from.
- [ ] `pip install -r requirements.txt` has been run.
- [ ] You have read the annotation guidelines at least once, so you know what a useful
      comment looks like. **Do not collect posts you would not label.**

---

## 3. Picking the posts

Per source account:

| Rule | Value |
|---|---|
| Which posts | The **most recent** 8\u201312 public posts, walking backwards from today |
| Why most recent | The recent window is where citizen requests concentrate, and it is reproducible |
| No cherry-picking | Do **not** select posts by comment richness. Take the window as it comes. |
| Log the window | Record the post URLs in the snapshot. |

Writing down the post URLs is what makes the sample auditable. A reviewer can check
that you did not select the unusually argumentative thread.

---

## 4. Capturing a post

For each post URL:

1. Open the post in your Chrome.
2. Scroll the comment section down slowly until the thread stops growing. Facebook and
   YouTube both load comments lazily; **a thread that is not fully scrolled is a
   truncated thread**, and the truncated comments are silently missing from the dataset.
3. Read the comment nodes out of the DOM. Each comment needs:
   - `comment_text` \u2014 the text, verbatim, with emoji and typos intact
   - `author_name` \u2014 the display name (used only to detect agency accounts)
   - `timestamp_raw` \u2014 the relative time as displayed
   - `is_reply` \u2014 true for a reply
   - `parent_comment_text` \u2014 the text of the comment it replies to, for replies
4. Also capture the **post itself**:
   - `post_url`, `post_text` (the caption), `post_date`, `post_media_type`, `post_topic`
5. Write it all into the snapshot JSON (format below).

**`post_text` is not optional.** It is the context the annotator needs, and without it a
large share of replies cannot be labeled at all.

### Scroll discipline

Comment threads on these accounts run long. A practical rule:

- Scroll until the comment count stops increasing for two consecutive scrolls.
- Then scroll a further three times to be sure.
- Record `scrolled_to_end: true` in the snapshot. If you did not reach the end, record
  `scrolled_to_end: false` and the count you stopped at.

A snapshot with `scrolled_to_end: false` is a partial capture. It is usable, but it must
say so.

---

## 5. The raw snapshot format

Write one JSON file per run. This is the contract between the browser agent and the
pipeline \u2014 if the shape is wrong, `to_interim.py` refuses it rather than silently
dropping comments.

```json
{
  "run_id": "fb_dost_pagasa_2026-10-20T09-30",
  "source_page": "dost_pagasa",
  "source_page_name": "DOST-PAGASA",
  "platform": "facebook",
  "agency_id": "dost_pagasa",
  "collection_method": "browser_dom_session",
  "tool": "orca-computer-use",
  "tool_version": "1.0",
  "user_agent": "<the browser's UA string>",
  "delay_seconds": 3,
  "collected_at": "2026-10-20T09:30:00+00:00",
  "notes": "",
  "posts": [
    {
      "post_id": "",
      "post_url": "https://www.facebook.com/PAGASA.DOST.GOV.PH/posts/123456",
      "post_date": "2026-10-19",
      "post_text": "SYABAS: Moderate rainfall expected over Northern Luzon.",
      "post_media_type": "text",
      "post_topic": "weather",
      "scrolled_to_end": true,
      "comments": [
        {
          "comment_text": "Please repair the damaged road in our barangay.",
          "author_name": "Juan Dela Cruz",
          "timestamp_raw": "2 hours ago",
          "is_reply": false,
          "parent_comment_text": ""
        },
        {
          "comment_text": "Same, please fix ours too.",
          "author_name": "Maria Santos",
          "timestamp_raw": "1 hour ago",
          "is_reply": true,
          "parent_comment_text": "Please repair the damaged road in our barangay."
        }
      ]
    }
  ]
}
```

| Field | Required | Notes |
|---|---|---|
| `run_id` | yes | Unique per run. `fb_<source_page>_<timestamp>` |
| `source_page` | yes | Must match the registry slug |
| `platform` | yes | `facebook` \| `youtube` \| `reddit` \| `x` |
| `agency_id` | yes | Must match the registry |
| `collection_method` | yes | `browser_dom_session` |
| `posts[]` | yes | One entry per post captured |
| `posts[].post_url` | yes | The permalink |
| `posts[].post_text` | yes | The caption. **Not optional.** |
| `posts[].comments[]` | yes | One entry per comment |
| `comments[].comment_text` | yes | Verbatim |
| `comments[].author_name` | no | Used only to detect agency accounts |
| `comments[].parent_comment_text` | for replies | The text it replies to |

`post_id` and `comment_id` are **generated** by the pipeline, not by you. Leave `post_id`
empty.

---

## 6. Turning a capture into pipeline input

```bash
python src/collect/to_interim.py \\
    --snapshot-dir data/raw/facebook \\
    --source-page dost_pagasa \\
    --platform facebook \\
    --agency-id dost_pagasa
```

This validates every snapshot, writes the two interim files, and appends a row to
`data/provenance/collection_log.csv`.

**If it reports problems, it writes nothing.** That is deliberate \u2014 a malformed capture
should not half-overwrite your interim layer. Fix the snapshot and run it again.

---

## 7. Then clean

```bash
python src/clean/pipeline.py \\
    --pool       data/interim/comments_captured.csv \\
    --out        data/processed/candidate_pool.csv \\
    --ledger-out data/interim/exclusion_ledger.csv \\
    --report     data/interim/cleaning_report.json
```

The report's `n_loaded` must equal `n_kept + n_excluded`. If it does not, something
dropped a row silently \u2014 that is a bug, not a rounding difference.

---

## 8. The pilot first

### Pilot results (2026-10-20)

The pilot was run through `src/collect/orca_fb.py` on two accounts, two posts each.

| Account | Posts | Comments captured | After cleaning |
|---|---|---|---|
| DOST-PAGASA | 2 | 37 | 36 |
| DSWD | 2 | 25 | 24 |
| **Total** | **4** | **62** | **60** |

2 comments were removed as `X_SPAM`. The line-count reconciliation held.

**Comments per post: 6, 18, 1 and 37.** The spread is wide — a newly posted
bulletin has almost no comments, an established post has dozens. Extrapolating from
the 4 pilot posts is not safe; a real yield estimate needs the full 8–12 posts per
account.

**Request-marker rate: 20 of 60 (33%).** That is a healthy spread, not a class of
all-requests, and it is consistent with the study's target of 15–65% actionable.

**Everything works end to end.** The chain ran: capture → `to_interim` → clean →
60 usable comments in `data/processed/candidate_pool.csv`.

### What the pilot did not settle

- **Yield per post is unproven.** 6, 18, 1 and 37 comments per post. Whether 10
  accounts × 8 posts reaches 600 Facebook comments is still an open question.
- **Replies were not detected** in the pilot (`is_reply` was false throughout), so
  the reply-parent capture path is untested.
- **Only 2 of the 10 accounts** have been touched.

### Running the pilot

```bash
python src/collect/orca_fb.py \
    --page https://www.facebook.com/PAGASA.DOST.GOV.PH \
    --source-page dost_pagasa --agency-id dost_pagasa \
    --source-page-name "DOST-PAGASA" --posts 2
```

Then convert and clean as in §6 and §7.

**Before collecting the full set, run a pilot: 2 accounts \u00d7 2 posts each.**

The pilot answers one question: **is the comment volume per post high enough to reach the
target?**

| Measure | Why it matters |
|---|---|
| Comments per post | If a post yields 15 comments, 8\u201312 posts per account gives 120\u2013180. Ten accounts would clear 1,000. If a post yields 3, no realistic source count reaches 1,000. |
| Actionable rate | If 80% of comments are requests, the class is skewed and you need more non-request posts. |
| `scrolled_to_end` rate | If threads are not scrolling to the end, the scraper is missing data. |
| Capture time per post | Sets the schedule for the full run. |

**Record the pilot numbers before the full run.** They are the evidence that the sample
was planned rather than assembled by convenience.

---

## 9. Rules that protect the dataset

- **Capture everything, filter later.** Do not skip a comment because it looks like
  spam or is not a request. The cleaning stage does that, with a reason code. A
  hand-skipped comment is an invisible bias.
- **One post, one snapshot.** Do not merge posts into a single capture. The split is
  grouped by post, and a merged capture makes the grouping unverifiable.
- **Never edit a raw snapshot.** If a capture is wrong, delete it and re-capture. The raw
  layer is the audit trail.
- **Log every run.** An unlogged run cannot be reported in the write-up.
- **Do not collect a post you have already collected.** The dedup stage would catch it,
  but the run log would not.

---

## 10. After the full collection

- [ ] `n_loaded == n_kept + n_excluded` in the cleaning report
- [ ] Every run appears in `data/provenance/collection_log.csv`
- [ ] The candidate pool has \u2265 600 Facebook comments (the primary dataset minimum)
- [ ] The class rate sits between 15% and 65% actionable
- [ ] Every source page has \u2265 40 usable comments
- [ ] The pilot numbers are written down for the Methodology section
