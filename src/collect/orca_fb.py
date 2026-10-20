"""
orca_fb.py — collect Facebook comments through orca computer-use.

Drives the researcher's own signed-in Chrome. No API key, no token, no copy of
the browser profile: orca reads the accessibility tree of the live window.

Two things this file exists to get right:

1. NAVIGATION. Facebook is an SPA and swallows failed navigations silently, so
   the address bar holding a URL is not evidence anything happened. The only
   reliable check is the loaded document URL.

2. THREAD DEPTH. A post's comment list grows lazily and slowly. Stopping when
   the count holds still for a few scrolls catches the first ten comments and
   calls it the whole thread. The scroll loop here keeps going until the count
   has been stable for several rounds AND a floor of scroll actions has passed.

Usage
-----
    python src/collect/orca_fb.py --page https://www.facebook.com/dswdserves \\
        --source-page dswd --agency-id dswd --posts 2

    python src/collect/orca_fb.py --discover-only \\
        --page https://www.facebook.com/dswdserves --source-page dswd
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW_DIR = os.path.join(ROOT, "data", "raw", "facebook")

WIN = "3149178"
APP = "chrome"

# --- scroll tuning ---------------------------------------------------------
# One `scroll --pages N` call scrolls N viewport heights in a single round
# trip, which is roughly a third of the cost of N separate wheel actions.
PAGES_PER_CALL = 3
MAX_ROUNDS = 25            # hard cap on rounds
STABLE_ROUNDS = 4          # rounds of no growth before we call it done
MIN_SCROLL_CALLS = 8       # never stop before this many scroll calls
SCROLL_PAUSE = 0.7

POST_URL_RE = re.compile(r"https?://www\.facebook\.com/[^\s,]*?/posts/[^\s,?]+")
PFBID_RE = re.compile(r"/posts/(pfbid[0-9A-Za-z]+)")
NODE_RE = re.compile(r"^(\t*)(\d+)\s+(\S+)\s*(.*)$")
DATE_RE = re.compile(
    r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+\w+\s+\d{1,2},\s+\d{4}"
    r"|^\d+\s+(minutes?|hours?|days?|weeks?|months?|years?)\s+ago", re.IGNORECASE)

# Page chrome that shows up among the text nodes before the caption
UI_NOISE = {
    "New notification in settings",
    "Facebook",
    "Home",
    "Reels",
    "Marketplace",
    "Gaming",
    "Notifications",
    "Your profile",
    "See more",
}


# ===========================================================================
# orca plumbing
# ===========================================================================

def orca(*args, timeout=120):
    cmd = ["orca", "computer"] + list(args) + ["--json"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       encoding="utf-8", errors="replace")
    try:
        return json.loads(r.stdout)
    except Exception:
        return {"ok": False, "error": {"message": (r.stdout or "")[:300]}}


def state(retries=3, pause=1.5):
    """The accessibility tree. Screenshots off: they triple the cost and the
    tree is what the extractor uses.

    The orca runtime occasionally drops a read while the page is loading, so
    a failed read is retried rather than treated as an empty page.
    """
    for _ in range(retries):
        st = orca("get-app-state", "--app", APP, "--window-id", WIN, "--no-screenshot")
        if st.get("ok"):
            snap = st["result"]["snapshot"]
            tree = snap.get("treeText", "")
            if tree:
                return tree
        time.sleep(pause)
    return None


def _norm(u):
    from urllib.parse import urlparse
    if not u:
        return None
    p = urlparse(u if "//" in u else "https://facebook.com" + u)
    return (p.path or "/").rstrip("/").lower()


def doc_url():
    """The URL of the loaded page.

    The document element carries it, but the tree is not always ready enough
    to expose one, so fall back to the address bar. The address bar can
    briefly hold the URL that was requested rather than the one that
    loaded, so it is the second choice, not the first.
    """
    t = state()
    if t:
        m = re.search(r"\bdocument\b[^\n]*?(https?://[^\s,]+)", t)
        if m:
            return m.group(1)
        m = re.search(r"edit Address and search bar\s*(https?://[^\s,]+)", t)
        if m:
            return m.group(1)
    return None


def address_bar_index():
    t = state()
    if not t:
        return None
    for line in t.splitlines():
        m = re.search(r"^\s*(\d+) edit Address and search bar", line)
        if m:
            return int(m.group(1))
    return None


def title_keyword(url: str) -> str:
    """A word that must appear in the window title once the page has loaded.

    Facebook titles look like "DOST-PAGASA - This year's World Environment Day
    celebration... | Facebook" and "DOST-PAGASA | Quezon City", so the page
    slug is a reliable keyword for both the page and any of its posts.
    """
    tail = url.split("facebook.com/")[-1].split("?")[0].strip("/")
    slug = tail.split("/")[0] if tail else ""
    return slug.replace(".", "").replace("-", "").lower() or ""


def window_title():
    """The window title.

    Cheaper and steadier than reading a URL out of the tree, and it is what a
    human would check to confirm a page loaded.
    """
    w = orca("list-windows", "--app", APP)
    if not w.get("ok"):
        return None
    for win in w["result"]["windows"]:
        if str(win.get("id")) == WIN:
            return win.get("title") or ""
    return None


def navigate(url, tries=3, settle=6, expect=None, expect_title=None, verbose=False):
    """Focus the omnibox, set the URL, drop the inline autocomplete, go.

    The sequence that works in Chrome:
      Ctrl+L  -> set-value  -> Delete  -> Return
    `paste-text` lets the omnibox inline-autocomplete to a shorter, different
    URL. `Delete` after set-value drops the autocompleted suffix.

    Verification is on the window TITLE when a keyword is given: it is one
    cheap call and does not depend on the tree being ready. The document URL
    is the fallback.
    """
    want = _norm(expect if expect else url)
    kw = (expect_title or "").lower()
    last = None
    for attempt in range(tries):
        # --restore-window: keyboard input needs the target window focused, and
        # running this from a terminal takes the focus away from Chrome.
        if not orca("hotkey", "--app", APP, "--window-id", WIN,
                    "--key", "CmdOrCtrl+L", "--restore-window").get("ok"):
            time.sleep(1.2)
            continue
        time.sleep(0.4)
        idx = address_bar_index()
        if idx is None:
            time.sleep(1.2)
            continue
        if not orca("set-value", "--app", APP, "--window-id", WIN,
                    "--element-index", str(idx), "--value", url).get("ok"):
            time.sleep(0.8)
            continue
        time.sleep(0.3)
        orca("press-key", "--app", APP, "--window-id", WIN, "--key", "Delete")
        time.sleep(0.2)
        if not orca("press-key", "--app", APP, "--window-id", WIN,
                    "--key", "Return").get("ok"):
            time.sleep(1.2)
            continue
        for _ in range(6):
            time.sleep(settle / 6)
            # The DOCUMENT element carries the URL that actually loaded. The
            # address bar only shows what was requested, so it cannot prove
            # the page moved.
            cur = _norm(doc_url())
            last = cur
            if cur and want and cur == want:
                return True, f"ok (attempt {attempt + 1})"
            if kw and cur is None:
                title = (window_title() or "").lower()
                if kw in title:
                    return True, f"ok (attempt {attempt + 1}, by title)"
        if verbose:
            print(f"      attempt {attempt + 1}: last={last} want={want or kw}")
        time.sleep(1)
    return False, f"did not take: last={last} want={want or kw}"


def scroll(pages=1, direction="down", x=400, y=600, pause=SCROLL_PAUSE):
    """Scroll `pages` viewport heights in one call."""
    orca("scroll", "--app", APP, "--window-id", WIN, "--direction", direction,
         "--x", str(x), "--y", str(y), "--pages", str(pages), "--no-screenshot")
    time.sleep(pause)


# ===========================================================================
# accessibility-tree parsing
# ===========================================================================

def parse_nodes(tree):
    nodes = []
    for line in tree.splitlines():
        m = NODE_RE.match(line)
        if not m:
            continue
        tabs, nid, role, rest = m.groups()
        value = ""
        vm = re.search(r"Value:\s*([^,]+)", rest)
        if vm:
            value = vm.group(1).strip()
            rest = rest[:vm.start()].rstrip(", ").strip()
        nodes.append((len(tabs), int(nid), role, rest, value))
    return nodes


def _is_comment(role, name):
    return role == "article" and name.startswith("Comment by ")


def extract_comments(tree):
    """Pull the comment threads out of the tree.

    A comment looks like:
        article Comment by <Author> <relative time>
            link <Author>, Value: <profile>?comment_id=...
            link <date>, Value: <post url>?comment_id=...
            text <body>
            Unlabeled graphic <emoji>. To get missing image descriptions, ...
            link #Hashtag, Value: ...
            button Hide or report this / Like / React / Reply
    """
    nodes = parse_nodes(tree)
    if not nodes:
        return []

    comment_depths = [n[0] for n in nodes if _is_comment(n[2], n[3])]
    top_depth = min(comment_depths) if comment_depths else 0

    comments = []
    i = 0
    while i < len(nodes):
        depth, _nid, role, name, _value = nodes[i]
        if not _is_comment(role, name):
            i += 1
            continue

        m = re.match(r"Comment by (.+?)(?:\s+(\d+\s+\w+\s+ago|\w+\s+ago))?$", name)
        author = (m.group(1).strip() if m else "")
        rel_time = (m.group(2).strip() if m else "")

        j = i + 1
        parts = []
        timestamp = ""
        permalink = ""
        edited = False
        translated = False
        while j < len(nodes) and nodes[j][0] > depth:
            _d2, _id2, role2, name2, value2 = nodes[j]
            if _is_comment(role2, name2):
                break
            if role2 == "link":
                if DATE_RE.match(name2):
                    timestamp = name2
                    permalink = value2
                elif name2.startswith("#"):
                    parts.append(name2)
            elif role2 == "text":
                if name2.strip():
                    parts.append(name2.strip())
            elif role2 == "button":
                low = name2.lower()
                if low == "edited":
                    edited = True
                elif low == "see translation":
                    translated = True
                elif "sticker" in low or "moodies" in low:
                    # an emoji/sticker-only comment: keep the description so the
                    # row is not silently empty
                    parts.append(name2)
            elif role2.startswith("Unlabeled graphic"):
                g = re.match(r"Unlabeled graphic (.+?)(?:\.\s*To get missing|$)", name2)
                if g:
                    parts.append(g.group(1).strip())
            j += 1

        text = " ".join(p for p in parts if p).strip()
        comments.append({
            "comment_text": text,
            "author_name": author,
            "timestamp_raw": timestamp or rel_time,
            "permalink": permalink,
            "is_reply": depth > top_depth,
            "edited": edited,
            "has_translation": translated,
        })
        i = j
    return comments


def extract_post_text(tree):
    """The post caption.

    The tree before the first comment mixes three things: the page chrome
    (a "New notification in settings" toast, the nav), the post header (the
    author link, the "Verified account" heading, and Facebook's obfuscated
    permalink whose characters are separated by zero-width spaces), and the
    caption itself.

    The caption starts after the author link and the account heading, and runs
    to the first comment. In-caption links (a hashtag, a named programme) are
    part of the caption and are kept; the obfuscated permalink and the
    "May be an image of ..." alt text are not.
    """
    nodes = parse_nodes(tree)
    parts = []
    started = False
    for _depth, _nid, role, name, _value in nodes:
        if _is_comment(role, name):
            break
        if not started:
            # the caption begins after the post's own identity block
            if role == "link" and name.endswith("view story"):
                started = True
            elif role == "heading" and "Verified account" in name:
                started = True
            continue
        if role == "text" and name.strip():
            if name.strip() in UI_NOISE:
                continue
            parts.append(name.strip())
        elif role == "link" and name.strip():
            if "\u200b" in name or "May be an image of" in name:
                continue
            if name.startswith("#"):
                parts.append(name.strip())
    return " ".join(parts).strip()


# ===========================================================================
# discovery and capture
# ===========================================================================

def discover_posts(page_url, limit=12, rounds=12):
    """Scroll the page feed and collect the post permalinks it exposes."""
    fb_ok, msg = navigate(page_url, expect_title=title_keyword(page_url))
    if not fb_ok:
        return [], msg
    time.sleep(4)
    urls = set()
    base = page_url.split("facebook.com/")[-1].split("?")[0].rstrip("/")
    for _ in range(rounds):
        scroll(3, pause=0.8)
        t = state()
        if not t:
            continue
        found = set(POST_URL_RE.findall(t))
        for p in PFBID_RE.findall(t):
            found.add(f"https://www.facebook.com/{base}/posts/{p}")
        urls |= found
        if len(urls) >= limit * 2:
            break
    return sorted(u.split("?")[0] for u in urls), f"{len(urls)} url(s)"


def capture_post(url, verbose=False):
    """Open a post, load the whole thread, read it."""
    ok, msg = navigate(url, expect_title=title_keyword(url))
    if not ok:
        return None, msg
    time.sleep(3)

    last = 0
    stable = 0
    calls = 0
    rounds = 0
    for rounds in range(1, MAX_ROUNDS + 1):
        scroll(PAGES_PER_CALL, pause=SCROLL_PAUSE)
        calls += 1
        t = state()
        if not t:
            continue
        n = t.count("Comment by ")
        if n == last and n > 0:
            stable += 1
        else:
            stable = 0
        if verbose and (n != last):
            print(f"        comments={n} (scroll calls={calls})")
        last = max(last, n)
        if stable >= STABLE_ROUNDS and calls >= MIN_SCROLL_CALLS:
            break

    t = state() or ""
    return {
        "tree": t,
        "n_comments": t.count("Comment by "),
        "scroll_actions": calls * PAGES_PER_CALL,
        "scroll_calls": calls,
        "rounds": rounds,
        "scrolled_to_end": stable >= STABLE_ROUNDS,
        "url": doc_url(),
    }, "ok"


def build_snapshot(source_page, source_page_name, agency_id, entries, notes=""):
    posts = []
    for url, cap in entries:
        tree = cap.get("tree", "")
        comments = extract_comments(tree)
        posts.append({
            "post_id": "",
            "post_url": url,
            "post_date": "",
            "post_text": extract_post_text(tree),
            "post_media_type": "text",
            "post_topic": "",
            "scrolled_to_end": cap.get("scrolled_to_end", False),
            "scroll_actions": cap.get("scroll_actions", 0),
            "comments": [{
                "comment_text": c["comment_text"],
                "author_name": c["author_name"],
                "timestamp_raw": c["timestamp_raw"],
                "is_reply": c["is_reply"],
                "parent_comment_text": "",
                "permalink": c["permalink"],
                "edited": c["edited"],
                "has_translation": c["has_translation"],
            } for c in comments],
        })
    return {
        "run_id": f"fb_{source_page}_{datetime.now().strftime('%Y-%m-%dT%H-%M')}",
        "source_page": source_page,
        "source_page_name": source_page_name,
        "platform": "facebook",
        "agency_id": agency_id,
        "collection_method": "browser_dom_session",
        "tool": "orca-computer-use",
        "tool_version": "1.0",
        "user_agent": "",
        "delay_seconds": 3,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "notes": notes,
        "posts": posts,
    }


def write_snapshot(snap, outdir=RAW_DIR):
    d = os.path.join(outdir, snap["source_page"])
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{snap['run_id']}.json")
    io.open(path, "w", encoding="utf-8", newline="").write(
        json.dumps(snap, ensure_ascii=False, indent=2))
    return path


# ===========================================================================
# CLI
# ===========================================================================

def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="Collect Facebook comments via orca")
    ap.add_argument("--page", required=True)
    ap.add_argument("--source-page", required=True)
    ap.add_argument("--agency-id", default="")
    ap.add_argument("--source-page-name", default="")
    ap.add_argument("--posts", type=int, default=2)
    ap.add_argument("--discover-only", action="store_true")
    ap.add_argument("--notes", default="")
    args = ap.parse_args(argv)

    print(f"discovering posts on {args.page}")
    urls, msg = discover_posts(args.page, limit=args.posts)
    print(f"  {msg}")
    for u in urls:
        print("   ", u)
    if args.discover_only:
        return 0
    if not urls:
        print("no post urls found")
        return 1

    entries = []
    for u in urls[:args.posts]:
        print(f"\ncapturing {u}")
        cap, m = capture_post(u, verbose=True)
        if cap is None:
            print("  FAILED:", m)
            continue
        cs = extract_comments(cap["tree"])
        print(f"  actions={cap['scroll_actions']} end={cap['scrolled_to_end']} "
              f"comments={cap['n_comments']} parsed={len(cs)}")
        for c in cs[:5]:
            print(f"    - [{c['author_name'][:26]:26}] {c['comment_text'][:78]!r}")
        if len(cs) > 5:
            print(f"    ... and {len(cs) - 5} more")
        entries.append((u, cap))
        time.sleep(2)

    if not entries:
        print("nothing captured")
        return 1
    snap = build_snapshot(args.source_page, args.source_page_name, args.agency_id,
                          entries, args.notes)
    path = write_snapshot(snap)
    n = sum(len(p["comments"]) for p in snap["posts"])
    print(f"\nSNAPSHOT -> {path}")
    print(f"  {len(snap['posts'])} post(s), {n} comment(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
