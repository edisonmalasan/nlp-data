"""
orca_browser.py — collect comments through Orca's built-in browser.

This is the primary collector. It drives the browser that Orca manages for this
worktree, using the account the researcher has already signed into, and reads
the page with JavaScript.

Why this route and not OS-level automation:

  * It does not need the window focused, so the researcher can keep working.
  * It reads the real DOM, not an accessibility tree, so the text is exact
    and there is no node cap to truncate a long thread.
  * No API key, no access token, no copy of the browser profile.

Usage
-----
    python src/collect/orca_browser.py \\
        --account https://www.facebook.com/PAGASA.DOST.GOV.PH \\
        --source-page dost_pagasa --agency-id dost_pagasa \\
        --source-page-name "DOST-PAGASA" --posts 2

    # collect from a different platform tab
    python src/collect/orca_browser.py --tab-index 1 --platform youtube ...
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
RAW_DIR = os.path.join(ROOT, "data", "raw")
JS_DIR = os.path.join(ROOT, "src", "collect")

# The selector that identifies one comment, per platform. The collector uses it
# to find the scrollable element that holds the thread and to count comments.
COMMENT_SELECTOR = {
    "facebook": 'div[role="article"][aria-label^="Comment by"]',
    "youtube": "ytd-comment-renderer",
    "x": 'article[data-testid="tweet"]',
    "reddit": 'shreddit-comment, div[data-testid="comment"]',
}

# The selector for one source post, per platform, used when discovering URLs.
POST_LINK_SELECTOR = {
    "facebook": 'a[href*="/posts/"]',
    "youtube": 'a[href*="/watch?v="]',
    "x": 'a[href*="/status/"]',
    "reddit": 'a[href*="/comments/"]',
}

# How long to wait for a page to settle, and when to give up on a thread.
PAGE_SETTLE = 2.5
MAX_SETTLE_ROUNDS = 20
SCROLL_STABLE_ROUNDS = 4
MIN_SCROLL_ROUNDS = 8
SCROLL_PAUSE = 1.2

FB_POST_RE = re.compile(r"https?://www\.facebook\.com/[^\s,]*?/posts/[^\s,?]+")


# ===========================================================================
# the orca CLI
# ===========================================================================

class OrcaError(RuntimeError):
    pass


def orca(*args, timeout=180):
    """Call the orca CLI. Always returns a dict.

    `--json` is added automatically: without it the CLI prints a
    human-readable table that will not parse.
    """
    argv = list(args)
    if "--json" not in argv:
        argv.append("--json")
    r = subprocess.run(["orca"] + argv, capture_output=True, text=True,
                       timeout=timeout, encoding="utf-8", errors="replace")
    out = (r.stdout or "").strip()
    try:
        parsed = json.loads(out)
    except Exception:
        raise OrcaError(f"orca {argv[0]}: unparseable output: {out[:300]}")
    if not isinstance(parsed, dict):
        return {"ok": True, "result": {"result": parsed}}
    if not parsed.get("ok"):
        err = parsed.get("error") or {}
        raise OrcaError(f"orca {argv[0]}: {err.get('code', '')} {err.get('message', '')}")
    return parsed


def eval_json(page: str, js: str, timeout=180):
    """Evaluate JS in a tab and decode the JSON it returns."""
    r = orca("eval", "--page", page, "--expression", js, timeout=timeout)
    res = r.get("result", {}) or {}
    val = res.get("result")
    if val is None:
        for k in ("value", "data", "output", "text"):
            if k in res:
                val = res[k]
                break
    if isinstance(val, str):
        try:
            return json.loads(val)
        except Exception:
            raise OrcaError(f"eval returned unparseable JSON: {val[:300]}")
    return val


# ===========================================================================
# tabs
# ===========================================================================

def list_tabs():
    r = orca("tab", "list")
    return (r.get("result", {}) or {}).get("tabs", []) or []


def pick_tab(tabs, index=None, url_contains=None):
    if index is not None:
        for t in tabs:
            if t.get("index") == index:
                return t
        raise OrcaError(f"no tab at index {index}")
    if url_contains:
        for t in tabs:
            if url_contains in (t.get("url") or ""):
                return t
    return tabs[0] if tabs else None


# ===========================================================================
# page control
# ===========================================================================

def goto(page: str, url: str, settle: float = PAGE_SETTLE):
    orca("goto", "--page", page, "--url", url)
    time.sleep(settle)


SCROLL_JS = r"""
(() => {
  const SEL = __SEL__;
  const nodes = document.querySelectorAll(SEL);
  const n = nodes.length;

  // Bring the last comment into view: that is what makes the lazy loader
  // fetch the next page.
  if (n) {
    const last = nodes[n - 1];
    last.scrollIntoView({block: 'end'});
  }

  // A post permalink opens in an overlay whose comment list has its own
  // scroll container, and that container is NOT an ancestor of the comment
  // nodes, so it has to be found by asking the DOM which scrollable element
  // actually holds the comments.
  let target = null;
  let best = 0;
  for (const el of document.querySelectorAll('div')) {
    const st = getComputedStyle(el);
    if (st.overflowY !== 'scroll' && st.overflowY !== 'auto') continue;
    if (el.scrollHeight <= el.clientHeight + 20) continue;
    const held = el.querySelectorAll(SEL).length;
    if (held > best) { best = held; target = el; }
  }
  if (target) {
    target.scrollTop = target.scrollHeight;
    return n + ':' + best;
  }

  // Otherwise the page itself scrolls. Step down rather than jumping to the
  // bottom, so the comment list is never skipped past.
  window.scrollBy(0, Math.floor(window.innerHeight * 0.85));
  return n + ':window';
})()
"""

REPLIES_JS = r"""
(() => {
  // "View N reply" expands a collapsed reply thread.
  let clicked = 0;
  for (const b of document.querySelectorAll('div[role="button"], span[role="button"]')) {
    const t = (b.innerText || '').trim();
    if (/^View \d+ repl/i.test(t)) { b.click(); clicked++; }
  }
  return clicked;
})()
"""


def scroll_to_bottom(page: str, platform: str = "facebook"):
    """Scroll the comment thread to its end. The comment list lazy-loads as it goes."""
    sel = COMMENT_SELECTOR.get(platform, COMMENT_SELECTOR["facebook"])
    js = SCROLL_JS.replace("__SEL__", sel)
    orca("eval", "--page", page, "--expression", js)
    time.sleep(SCROLL_PAUSE)


def expand_replies(page: str) -> int:
    """Click any 'View N replies' control so collapsed threads are opened."""
    try:
        r = orca("eval", "--page", page, "--expression", REPLIES_JS)
        res = (r.get("result", {}) or {}).get("result")
        return int(res or 0)
    except (OrcaError, ValueError):
        return 0


def comment_count(page: str, platform: str = "facebook") -> int:
    sel = COMMENT_SELECTOR.get(platform, COMMENT_SELECTOR["facebook"])
    v = eval_json(page,
                  f"document.querySelectorAll({json.dumps(sel)}).length")
    return int(v or 0)


def wait_for_comments(page: str, platform: str = "facebook",
                      min_count: int = 1, rounds: int = MAX_SETTLE_ROUNDS):
    for _ in range(rounds):
        n = comment_count(page, platform)
        if n >= min_count:
            return n
        time.sleep(1.2)
    return comment_count(page, platform)


def load_thread(page: str, platform: str = "facebook", min_count: int = 1):
    """Scroll until the comment count stops growing.

    A post's comment list grows lazily and slowly. Stopping when the count
    holds still for a few rounds catches the first handful and calls it the
    whole thread, so there is a floor on how much scrolling happens.
    """
    n = wait_for_comments(page, platform, min_count)
    last = n
    stable = 0
    for rnd in range(1, MAX_SETTLE_ROUNDS + 1):
        scroll_to_bottom(page, platform)
        expand_replies(page)
        n = comment_count(page, platform)
        if n == last and n > 0:
            stable += 1
        else:
            stable = 0
        last = max(last, n)
        if stable >= SCROLL_STABLE_ROUNDS and rnd >= MIN_SCROLL_ROUNDS:
            break
    # whether the thread was actually scrolled to its end, which the protocol
    # records so a partial capture is visible rather than silent
    return last, (stable >= SCROLL_STABLE_ROUNDS and rnd >= MIN_SCROLL_ROUNDS)


# ===========================================================================
# facebook
# ===========================================================================

EXTRACTOR_FILES = {
    "facebook": "extract_facebook.js",
    "youtube": "extract_youtube.js",
    "x": "extract_x.js",
    "reddit": "extract_reddit.js",
}


def load_extract_js(name="extract_facebook.js"):
    with io.open(os.path.join(JS_DIR, name), encoding="utf-8") as fh:
        return fh.read()


def post_links_js(platform: str) -> str:
    sel = POST_LINK_SELECTOR.get(platform, POST_LINK_SELECTOR["facebook"])
    return (
        "(() => {\n"
        "  const out = []; const seen = new Set();\n"
        f"  for (const a of document.querySelectorAll({json.dumps(sel)})) {{\n"
        "    const href = (a.getAttribute('href') || '').split('?')[0];\n"
        "    if (!href || seen.has(href)) continue;\n"
        "    seen.add(href); out.push(href);\n"
        "  }\n"
        "  return JSON.stringify(out);\n"
        "})()"
    )


def discover_posts(page: str, platform: str = "facebook",
                   limit: int = 12, rounds: int = 8):
    """Find recent post permalinks on an account.

    A Facebook page has a "Featured" carousel of older posts at the top and
    then the main feed, which runs newest first. The carousel posts are not
    recent, so the links are taken in DOM order and the LAST ones are used.
    """
    found = []
    seen = set()
    for _ in range(rounds):
        scroll_to_bottom(page, platform)
        try:
            urls = eval_json(page, post_links_js(platform)) or []
        except OrcaError:
            break
        for u in urls:
            if u not in seen:
                seen.add(u)
                found.append(u)
        if len(found) >= limit * 3:
            break
    # newest last in the feed, so take from the end
    return list(reversed(found))[:limit]


def capture_post(page: str, url: str, extract_js: str, platform: str = "facebook"):
    """Open a post, load the whole thread, extract it."""
    goto(page, url, settle=3.0)
    n_loaded, scrolled = load_thread(page, platform)
    data = eval_json(page, extract_js)
    if not isinstance(data, dict):
        raise OrcaError("extractor returned no data")
    data["post_url"] = url
    data["scrolled_to_end"] = scrolled
    data["n_loaded"] = n_loaded
    return data


def build_snapshot(source_page, source_page_name, agency_id, platform, entries,
                   tool_version="orca-cli", notes=""):
    posts = []
    for url, data in entries:
        p = data.get("post", {}) or {}
        posts.append({
            "post_id": "",
            "post_url": url,
            "post_date": p.get("post_date", ""),
            "post_text": p.get("post_text", ""),
            "post_media_type": "text",
            "post_topic": "",
            "n_comments": data.get("n_comments", 0),
            "scrolled_to_end": data.get("scrolled_to_end", False),
            "scroll_calls": data.get("n_loaded", 0),
            "comments": data.get("comments", []) or [],
        })
    return {
        "run_id": f"{platform}_{source_page}_{datetime.now().strftime('%Y-%m-%dT%H-%M')}",
        "source_page": source_page,
        "source_page_name": source_page_name,
        "platform": platform,
        "agency_id": agency_id,
        "collection_method": "browser_dom_session",
        "tool": tool_version,
        "tool_version": "1.0",
        "user_agent": "",
        "delay_seconds": 3,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "notes": notes,
        "posts": posts,
    }


def write_snapshot(snap, outdir=RAW_DIR):
    d = os.path.join(outdir, snap["platform"], snap["source_page"])
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
    ap = argparse.ArgumentParser(description="Collect comments through Orca's browser")
    ap.add_argument("--account", required=True,
                    help="the page URL to collect from, e.g. a Facebook page")
    ap.add_argument("--source-page", required=True)
    ap.add_argument("--agency-id", default="")
    ap.add_argument("--source-page-name", default="")
    ap.add_argument("--platform", default="facebook")
    ap.add_argument("--tab-index", type=int, default=None)
    ap.add_argument("--posts", type=int, default=2)
    ap.add_argument("--notes", default="")
    ap.add_argument("--dry-run", action="store_true",
                    help="discover the post URLs and stop")
    args = ap.parse_args(argv)

    tabs = list_tabs()
    if not tabs:
        print("no browser tabs found. open the page in the Orca browser first.")
        return 1
    print("tabs:")
    for t in tabs:
        print(f"   [{t.get('index')}] {t.get('title')!r} {t.get('url')}")

    tab = pick_tab(tabs, index=args.tab_index)
    page = tab["browserPageId"]
    print(f"\nusing tab [{tab.get('index')}] {tab.get('url')}")

    print(f"\nopening {args.account}")
    goto(page, args.account, settle=4.0)

    extract_js = load_extract_js(EXTRACTOR_FILES.get(args.platform,
                                                   "extract_facebook.js"))
    urls = discover_posts(page, args.platform, limit=args.posts)
    if args.platform == "youtube":
        # the channel's videos tab is what lists the videos
        goto(page, args.account.rstrip("/") + "/videos", settle=4.0)
        urls = discover_posts(page, "youtube", limit=args.posts)
    if not urls:
        urls = [args.account]

    print(f"\nfound {len(urls)} post url(s):")
    for u in urls:
        print("   ", u)
    if not urls:
        print("nothing discovered")
        return 1
    if args.dry_run:
        return 0

    entries = []
    for u in urls[:args.posts]:
        print(f"\ncapturing {u}")
        try:
            data = capture_post(page, u, extract_js, args.platform)
        except OrcaError as e:
            print("   FAILED:", e)
            continue
        print(f"   {data.get('n_comments', 0)} comment(s)")
        for c in (data.get("comments") or [])[:4]:
            print(f"     - [{c.get('author_name','')[:26]:26}] {c.get('comment_text','')[:80]!r}")
        entries.append((u, data))
        time.sleep(1.5)

    if not entries:
        print("nothing captured")
        return 1
    snap = build_snapshot(args.source_page, args.source_page_name, args.agency_id,
                          args.platform, entries, notes=args.notes)
    path = write_snapshot(snap)
    n = sum(p["n_comments"] for p in snap["posts"])
    print(f"\nSNAPSHOT -> {path}")
    print(f"  {len(snap['posts'])} post(s), {n} comment(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
