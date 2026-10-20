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
    "facebook": 'a[href*="/posts/"], a[href*="/reel/"], a[href*="/photo/"], '
                'a[href*="permalink.php"], a[href*="story_fbid"]',
    "youtube": 'a[href*="/watch?v="]',
    "x": 'a[href*="/status/"]',
    "reddit": 'a[href*="/comments/"]',
}

# A Facebook post is not always a /posts/ link. A page's feed is full of
# Reels and photo posts, and their permalinks are /reel/<id> and
# /photo/?fbid=<id>. Missing those loses most of the posts on some pages.
FACEBOOK_POST_RE = r"^https?://(?:www\.|m\.|l\.)?facebook\.com/.*?/(?:posts/|reel/|photo/)"

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
            # a plain string result, e.g. "clicked" - not an error
            return val
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


PAGE_TEXT_JS = r"""
(() => {
  const body = document.body.innerText || '';
  return JSON.stringify({
    url: location.href,
    title: document.title || '',
    body: body.slice(0, 4000),
    bodyLen: body.length,
    articles: document.querySelectorAll('div[role="article"]').length,
    links: document.querySelectorAll('a[href*="/posts/"]').length,
  });
})()
"""


def read_page(page: str) -> dict:
    """The rendered text of the page, with no screenshot."""
    try:
        v = eval_json(page, PAGE_TEXT_JS)
    except (OrcaError, ValueError):
        return {}
    return v if isinstance(v, dict) else {}


def wait_for_content(page: str, markers, timeout: float = 25.0, poll: float = 2.0) -> dict:
    """Wait until the page has rendered.

    Facebook serves the shell - the nav, the notification badge, the login
    prompt - before the profile content arrives. Reading the page too early
    gives the shell, whose title is always "(N) Facebook" and whose body
    contains a login prompt, so a page that has not rendered looks exactly
    like a page that is gated.

    A profile page is rendered when the body carries a follower count.
    """
    deadline = time.time() + timeout
    info = {}
    while time.time() < deadline:
        info = read_page(page)
        body = (info.get("body") or "")
        if any(m.lower() in body.lower() for m in markers):
            return info
        if any(b in body for b in ("This content isn't available",
                                   "You're Temporarily Blocked",
                                   "Page Not Found")):
            return info
        time.sleep(poll)
    return info


def profile_markers() -> list:
    """Strings that only appear on a rendered Facebook page."""
    return ["followers", "following", "Government organization", "Posts"]


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
  //
  // The same is true of a page feed: Facebook's new feed is a virtualized
  // list inside its own scroller, so window.scrollBy never moves it and the
  // feed appears to have no posts at all. Any scrollable element holding
  // articles is scrolled to its end.
  const scrollers = [];
  for (const el of document.querySelectorAll('div, ul, section')) {
    const st = getComputedStyle(el);
    if (st.overflowY !== 'scroll' && st.overflowY !== 'auto') continue;
    if (el.scrollHeight <= el.clientHeight + 20) continue;
    const held = el.querySelectorAll(SEL).length;
    const arts = el.querySelectorAll('div[role="article"]').length;
    if (held > 0 || arts > 0) scrollers.push({el: el, held: held, arts: arts});
  }
  // prefer the scroller that holds the most comments, then the most articles
  scrollers.sort((a, b) => (b.held - a.held) || (b.arts - a.arts));
  for (const s of scrollers.slice(0, 3)) {
    s.el.scrollTop = s.el.scrollHeight;
  }

  // The page itself may scroll too.
  window.scrollBy(0, Math.floor(window.innerHeight * 0.85));

  return n + ':' + scrollers.length;
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
    # the selector has to be a quoted JS string, not a bare token
    js = SCROLL_JS.replace("__SEL__", json.dumps(sel))
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


def load_thread(page: str, platform: str = "facebook", min_count: int = 1,
                wait_rounds: int = 0):
    """Scroll until the comment count stops growing.

    A post's comment list grows lazily and slowly. Stopping when the count
    holds still for a few rounds catches the first handful and calls it the
    whole thread, so there is a floor on how much scrolling happens.

    wait_rounds caps the initial wait for the thread to appear, so a post
    whose thread never renders does not cost the full wait before the
    fallback is tried.
    """
    n = wait_for_comments(page, platform, min_count,
                          rounds=wait_rounds or MAX_SETTLE_ROUNDS)
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
    """Collect the permalinks of the posts on the page.

    Facebook wraps outbound links in l.php?u=<encoded>, so those are
    unwrapped first, and a post is not always a /posts/ link: a page's feed is
    full of Reels and photo posts, whose permalinks are /reel/<id> and
    /photo/?fbid=<id>.
    """
    sel = POST_LINK_SELECTOR.get(platform, POST_LINK_SELECTOR["facebook"])
    if platform == "facebook":
        # A Facebook post is not always a /posts/ link. A page's feed is
        # full of photo posts, whose permalink is /photo/?fbid=<id>, and
        # many agencies post almost nothing else - so a selector that only
        # matches /posts/ finds no permalinks at all on those pages.
        #
        # The page's own tab links (/reel/?s=tab) look like permalinks and
        # are not posts, so each kind is checked for the id that proves it.
        return (
            "(() => {\n"
            "  const out = []; const seen = new Set();\n"
            "  const A = " + json.dumps(sel) + ";\n"
            "  const SEL = A.split(',').map(s => s.trim() + '[href]').join(',');\n"
            "  const anchors = document.querySelectorAll(SEL);\n"
            "  for (let k = 0; k < anchors.length; k++) {\n"
            "    const a = anchors[k];\n"
            "    let href = a.getAttribute('href') || '';\n"
            "    if (!href) continue;\n"
            "    if (href.indexOf('l.php?u=') !== -1) {\n"
            "      try { href = decodeURIComponent(href.split('u=')[1].split('&')[0]); } catch (e) {}\n"
            "    }\n"
            "    if (href.indexOf('//') === 0) { href = location.protocol + href; }\n"
            "    else if (href.charAt(0) === '/') { href = location.origin + href; }\n"
            "    if (href.indexOf('facebook.com') === -1) continue;\n"
            "    const path = href.split('?')[0].replace(/^https?:\\/\\/[^/]*facebook\\.com/, '');\n"
            "    const segs = path.split('/').filter(s => s.length);\n"
            "    let kind = null, tail = '';\n"
            "    for (let i = 0; i < segs.length; i++) {\n"
            "      if (segs[i] === 'posts' || segs[i] === 'reel' || segs[i] === 'photo') {\n"
            "        kind = segs[i]; tail = segs[i + 1] || ''; break;\n"
            "      }\n"
            "    }\n"
            "    if (!kind) {\n"
            "      if (/story_fbid=(\\d+)/.test(href)) {\n"
            "        const f = href.match(/story_fbid=(\\d+)/);\n"
            "        href = 'https://www.facebook.com/permalink.php?story_fbid=' + f[1];\n"
            "      } else { continue; }\n"
            "    } else if (kind === 'photo') {\n"
            "      const f = href.match(/fbid=(\\d+)/);\n"
            "      if (!f) continue;\n"
            "      href = 'https://www.facebook.com/photo/?fbid=' + f[1];\n"
            "    } else if (kind === 'reel') {\n"
            "      if (!tail) continue;\n"
            "      href = 'https://www.facebook.com/reel/' + tail;\n"
            "    } else {\n"
            "      if (!tail) continue;\n"
            "      href = 'https://www.facebook.com/posts/' + tail;\n"
            "    }\n"
            "    if (seen.has(href)) continue;\n"
            "    seen.add(href); out.push({u: href, i: k});\n"
            "  }\n"
            "  return JSON.stringify(out);\n"
            "})()"
        )
    return (
        "(() => {\n"
        "  const out = []; const seen = new Set();\n"
        "  const anchors = document.querySelectorAll(" + json.dumps(sel) + ");\n"
        "  for (let k = 0; k < anchors.length; k++) {\n"
        "    const a = anchors[k];\n"
        "    let href = a.getAttribute('href') || '';\n"
        "    if (!href) continue;\n"
        "    if (href.indexOf('//') === 0) { href = location.protocol + href; }\n"
        "    else if (href.charAt(0) === '/') { href = location.origin + href; }\n"
        "    // the query is NOT stripped: on YouTube the video id is the query,\n"
        "    // and dropping it turns every video into /watch\n"
        "    if (!href || seen.has(href)) continue;\n"
        "    seen.add(href); out.push({u: href, i: k});\n"
        "  }\n"
        "  return JSON.stringify(out);\n"
        "})()"
    )


POSTS_TAB_JS = r"""
(() => {
  // A page's feed only exposes a permalink for some of its posts, so the
  // reliable source is the page's own "Posts" tab, which lists them all in
  // order. Click it if it is not already selected.
  const wanted = /^posts$/i;
  for (const el of document.querySelectorAll(
        'a[role="tab"], div[role="tab"], [role="tablist"] a, a')) {
    const t = (el.innerText || '').trim();
    if (!wanted.test(t)) continue;
    const sel = el.getAttribute('aria-selected');
    if (sel === 'true') return 'already';
    el.click();
    return 'clicked';
  }
  return 'not found';
})()
"""


def find_inviting_posts(page: str, limit: int = 12, rounds: int = 6) -> list:
    """Find the posts on a page that invite citizen requests.

    The "most recent posts" stratum turned out to be dominated by
    announcements - typhoon bulletins and programme notices - where citizens
    react rather than ask. The posts that actually draw requests are the ones
    that invite them, so this is a second stratum rather than a replacement.

    Returns a list of permalinks.
    """
    js = open(os.path.join(JS_DIR, "find_invites.js"), encoding="utf-8").read()
    found = []
    seen = set()
    for _ in range(rounds):
        # the FEED has to be scrolled, not a comment thread: an account page
        # has no thread, so the thread scroller does nothing and only the
        # posts that happened to render are ever examined
        scroll_feed(page, "facebook")
        try:
            data = eval_json(page, js) or {}
        except OrcaError:
            break
        for u in data.get("urls", []):
            if u not in seen:
                seen.add(u)
                found.append(u)
        if len(found) >= limit * 2:
            break
    return found[:limit]


def open_posts_tab(page: str, platform: str = "facebook") -> str:
    """Open the account's chronological Posts tab, when it has one."""
    if platform != "facebook":
        return "n/a"
    try:
        r = orca("eval", "--page", page, "--expression", POSTS_TAB_JS)
        res = (r.get("result", {}) or {}).get("result")
        state = str(res or "")
        if state == "clicked":
            time.sleep(3.0)
        return state
    except (OrcaError, ValueError):
        return "error"


def discover_posts(page: str, platform: str = "facebook",
                   limit: int = 12, rounds: int = 8):
    """Find recent post permalinks on an account.

    A Facebook page has a "Featured" carousel of older posts at the top and
    then the main feed, which runs newest first. The carousel posts are not
    recent, so the links are taken in DOM order and the LAST ones are used.

    The page's own "Posts" tab is opened first, because the feed alone only
    exposes a permalink for some of the posts.
    """
    state = open_posts_tab(page, platform)
    if state == "clicked":
        time.sleep(1.5)

    # The page has to render before its posts exist. A YouTube channel or an
    # X timeline that has not hydrated has no items at all, and that looks
    # exactly like an account with no posts.
    READY = {
        "facebook": ["followers", "Posts"],
        "youtube": ["Video", "videos", "Shorts"],
        "x": ["Home", "Posts"],
        "reddit": ["post", "comments"],
    }
    wait_for_content(page, READY.get(platform, ["followers"]), timeout=25.0)

    found = []
    seen = set()
    for _ in range(rounds):
        # the feed has to be scrolled, not the comment thread
        scroll_feed(page, platform)
        try:
            urls = eval_json(page, post_links_js(platform)) or []
        except OrcaError:
            break
        for item in urls:
            u = item["u"] if isinstance(item, dict) else item
            if u not in seen:
                seen.add(u)
                found.append(u)
        if len(found) >= limit * 3:
            break
    # newest last in the feed, so take from the end
    return list(reversed(found))[:limit]


FEED_SCROLL_JS = r"""
(() => {
  // Scrolling a FEED is not the same as scrolling a comment thread.
  //
  // A Facebook feed, a YouTube channel and an X timeline are each a
  // virtualized list inside their own scroll container, and the container
  // only becomes scrollable once it has overflowed. On a page with a short
  // feed it has not overflowed yet, so the usual "scroll the scroller that
  // holds the articles" logic finds nothing to scroll, the feed never
  // grows, and the account looks like it has no posts at all.
  //
  // So: scroll the window first to make the layout taller, then scroll
  // every candidate container to its end whether or not it overflows, and
  // report how many items are in the feed now.
  window.scrollBy(0, Math.floor(window.innerHeight * 0.9));

  const ITEM = 'div[role="article"], ytd-rich-item-renderer, ' +
               'ytd-grid-video-renderer, ytd-video-renderer, ' +
               'article[data-testid="tweet"], shreddit-comment';
  const containers = new Set();
  const items = document.querySelectorAll(ITEM);
  for (const it of items) {
    let el = it.parentElement;
    let hops = 0;
    while (el && el !== document.body && hops < 12) {
      const st = getComputedStyle(el);
      if (st.overflowY === 'scroll' || st.overflowY === 'auto') {
        containers.add(el);
        break;
      }
      el = el.parentElement;
      hops++;
    }
  }
  for (const el of containers) {
    el.scrollTop = el.scrollHeight;
    el.dispatchEvent(new Event('scroll', {bubbles: true}));
  }
  window.scrollBy(0, Math.floor(window.innerHeight * 0.6));

  return JSON.stringify({
    items: items.length,
    containers: containers.size,
    y: Math.round(window.scrollY),
    h: Math.round(document.body.scrollHeight),
  });
})()
"""


def scroll_feed(page: str, platform: str = "facebook") -> dict:
    """Scroll an account's FEED, so more posts load.

    This is not the comment-thread scroll: that one looks for the thread's
    own scroller, which an account page does not have.
    """
    try:
        v = eval_json(page, FEED_SCROLL_JS)
    except (OrcaError, ValueError):
        return {}
    return v if isinstance(v, dict) else {}


VIEW_POST_JS = r"""
(() => {
  // A photo permalink opens a PREVIEW of the photo, not the post: the page
  // says "This photo is from a post" and the comment box is empty. The
  // post itself is behind the "View post" link, and that is where the
  // thread is.
  for (const a of document.querySelectorAll('a[href]')) {
    const t = (a.innerText || '').trim();
    const h = a.getAttribute('href') || '';
    if (/view post/i.test(t) && /\/posts\/|permalink/.test(h)) {
      return h.split('?')[0];
    }
  }
  return '';
})()
"""


def resolve_view_post(page: str, timeout: float = 0.0) -> str:
    """The real post permalink behind a photo preview, if there is one.

    The preview renders lazily, so the link is not there the instant the
    page arrives. With a timeout, the page is polled until it appears.
    """
    deadline = time.time() + timeout
    while True:
        try:
            v = eval_json(page, VIEW_POST_JS)
        except (OrcaError, ValueError):
            v = ""
        if isinstance(v, str) and v.strip():
            return v.strip()
        if time.time() >= deadline:
            return ""
        time.sleep(1.5)


# Facebook will not route a direct permalink navigation for this session:
# the browser lands on the home feed instead of the post, and the comment
# thread is never rendered. Clicking the permalink from the account's own
# feed opens the post in an overlay with the thread attached, which is how a
# person reads the comments anyway. The capture therefore falls back to the
# click when the direct navigation lands on the feed.
HOME_FEED_JS = r"""
(() => {
  const b = document.body.innerText || '';
  const onFeed = /What's on your mind|Create a post/i.test(b);
  const onPost = document.querySelectorAll('div[role="article"]').length > 1;
  return JSON.stringify({onFeed: onFeed, onPost: onPost,
                         bodyLen: b.length,
                         arts: document.querySelectorAll('div[role="article"]').length});
})()
"""

CLICK_PERMALINK_JS = r"""
(() => {
  const WANT = __WANT__;
  // the target may be a /posts/ link or a /photo/?fbid= link, and the feed
  // may carry either, so the post id is compared as well as the whole URL
  const wantId = (WANT.match(/fbid=(\d+)/) || [])[1] ||
                 (WANT.match(/pfbid([A-Za-z0-9]+)/) || [])[1] || '';
  for (const a of document.querySelectorAll('a[href]')) {
    let h = a.getAttribute('href') || '';
    if (!h) continue;
    if (h.indexOf('l.php?u=') !== -1) {
      try { h = decodeURIComponent(h.split('u=')[1].split('&')[0]); } catch (e) {}
    }
    const raw = h;
    h = h.split('?')[0];
    const myId = (raw.match(/fbid=(\d+)/) || [])[1] ||
                 (h.match(/pfbid([A-Za-z0-9]+)/) || [])[1] || '';
    if (h !== WANT && !(wantId && myId && myId === wantId)) continue;
    a.scrollIntoView({block: 'center'});
    a.click();
    return 'clicked';
  }
  return 'not found';
})()
"""


CLICK_INDEX_JS = r"""
(() => {
  const a = document.querySelectorAll('a[href]')[__IDX__];
  if (!a) return 'gone';
  a.scrollIntoView({block: 'center'});
  a.click();
  return 'clicked';
})()
"""

CLICK_VIEW_POST_JS = r"""
(() => {
  for (const a of document.querySelectorAll('a[href]')) {
    const t = (a.innerText || '').trim();
    if (/view post/i.test(t)) { a.click(); return 'clicked'; }
  }
  return 'not found';
})()
"""

CLOSE_OVERLAY_JS = r"""
(() => {
  for (const b of document.querySelectorAll('[aria-label="Close"], [aria-label="close"]')) {
    b.click();
    return 'closed';
  }
  document.dispatchEvent(new KeyboardEvent('keydown',
    {key: 'Escape', code: 'Escape', keyCode: 27, which: 27, bubbles: true}));
  document.body.dispatchEvent(new KeyboardEvent('keydown',
    {key: 'Escape', code: 'Escape', keyCode: 27, which: 27, bubbles: true}));
  return 'esc';
})()
"""


def click_index(page: str, idx: int) -> str:
    """Click the anchor at a DOM index, without navigating away."""
    js = CLICK_INDEX_JS.replace("__IDX__", str(int(idx)))
    try:
        v = eval_json(page, js)
    except (OrcaError, ValueError):
        return "failed"
    return v.strip() if isinstance(v, str) else "failed"


def click_view_post(page: str) -> str:
    """Click the "View post" link of a photo preview."""
    try:
        v = eval_json(page, CLICK_VIEW_POST_JS)
    except (OrcaError, ValueError):
        return "failed"
    return v.strip() if isinstance(v, str) else "failed"


def close_overlay(page: str) -> str:
    """Close the post overlay and return to the feed."""
    try:
        v = eval_json(page, CLOSE_OVERLAY_JS)
    except (OrcaError, ValueError):
        v = ""
    time.sleep(0.8)
    # Escape as well, in case the overlay ignored the click
    try:
        orca("keypress", "--key", "Escape", "--page", page)
    except OrcaError:
        pass
    time.sleep(0.8)
    return v.strip() if isinstance(v, str) else ""


def looks_like_home_feed(page: str) -> bool:
    """True when the browser is showing the home feed instead of the post."""
    try:
        v = eval_json(page, HOME_FEED_JS)
    except (OrcaError, ValueError):
        return False
    if not isinstance(v, dict):
        return False
    return bool(v.get("onFeed")) and not v.get("onPost")


def page_slug_from_url(url: str) -> str:
    """The page name out of a Facebook permalink: .../dpwhph/posts/x -> dpwhph."""
    m = re.search(r"facebook\.com/([^/?#]+)", url or "")
    if not m:
        return ""
    slug = m.group(1)
    if slug in ("photo", "permalink.php", "watch", "profile.php", "groups", "pages"):
        return ""
    return slug


def click_permalink(page: str, url: str, rounds: int = 8) -> str:
    """Click a permalink on the account page, scrolling the feed until it is there."""
    want = (url or "").split("?")[0]
    js = CLICK_PERMALINK_JS.replace("__WANT__", json.dumps(want))
    for _ in range(rounds):
        try:
            res = eval_json(page, js)
        except (OrcaError, ValueError):
            res = ""
        if res == "clicked":
            return "clicked"
        scroll_feed(page, "facebook")
        time.sleep(0.8)
    return "not found"


def capture_one(page: str, url: str, extract_js: str,
                platform: str = "facebook") -> dict:
    """Capture one post and its thread.

    A photo post's permalink is a PREVIEW: it says "This photo is from a
    post", shows an empty comment box, and carries a "View post" link to
    the post itself, where the thread is. Clicking the photo link on the
    account page navigates away instead, so the preview is opened and the
    real permalink read from it.

    If the post then loads without its thread - which Facebook does for a
    logged-in session - the account page is opened again and the permalink
    clicked there, which attaches the thread.
    """
    goto(page, url, settle=4.0)
    real = ""
    if platform == "facebook":
        real = resolve_view_post(page, timeout=10.0)
    if real and real != url:
        goto(page, real, settle=4.0)

    n_loaded, scrolled = load_thread(page, platform, wait_rounds=8)

    if platform == "facebook" and n_loaded == 0:
        slug = page_slug_from_url(url)
        if slug:
            goto(page, f"https://www.facebook.com/{slug}", settle=5.0)
            wait_for_content(page, ["followers", "Posts"], timeout=20.0)
            time.sleep(1.5)
            target = real if real else url
            if click_permalink(page, target, rounds=12) == "clicked":
                time.sleep(2.5)
                n_loaded, scrolled = load_thread(page, platform)
                if n_loaded == 0 and real:
                    if click_view_post(page) == "clicked":
                        time.sleep(2.0)
                        n_loaded, scrolled = load_thread(page, platform)

    try:
        data = eval_json(page, extract_js)
    except (OrcaError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    data["n_loaded"] = n_loaded
    data["scrolled_to_end"] = scrolled
    data["resolved_post_url"] = real
    return data


# ---------------------------------------------------------------------------
# YouTube
#
# The YouTube app does not always boot in a tab that is only being driven:
# the page title arrives but the content never renders, so there are no
# video links and no comments to read. The data is still in the page though.
# ytInitialData is not a global in that case - it is only in the page source -
# so it is parsed out of the HTML, and the comments come from the same public
# endpoint the page itself calls.
#
# Each script is one IIFE. An earlier version declared a helper at the top
# level, and orca eval shares the page's global scope, so the second call on
# the same page failed with "Identifier has already been declared".
# ---------------------------------------------------------------------------

YT_EXTRACT_FN = r"""
  const YT_EXTRACT = () => {
    if (window.ytInitialData) return window.ytInitialData;
    const h = document.documentElement.outerHTML || '';
    const marks = ['var ytInitialData = ', 'window["ytInitialData"] = ',
                   'ytInitialData = ', '"ytInitialData":'];
    for (const mark of marks) {
      const i = h.indexOf(mark);
      if (i < 0) continue;
      const start = h.indexOf('{', i);
      if (start < 0) continue;
      let depth = 0, inStr = false, esc = false, end = -1;
      for (let j = start; j < h.length && j < start + 8000000; j++) {
        const ch = h[j];
        if (inStr) {
          if (esc) esc = false;
          else if (ch === '\\') esc = true;
          else if (ch === '"') inStr = false;
          continue;
        }
        if (ch === '"') inStr = true;
        else if (ch === '{') depth++;
        else if (ch === '}') { depth--; if (depth === 0) { end = j + 1; break; } }
      }
      if (end > start) {
        try { return JSON.parse(h.slice(start, end)); } catch (e) {}
      }
    }
    return null;
  };
"""

YT_DISCOVER_JS = r"""
(() => {
__EXTRACT__
  const d = YT_EXTRACT() || {};
  const out = [];
  const seen = new Set();
  const walk = (node) => {
    if (!node || typeof node !== 'object') return;
    if (Array.isArray(node)) { for (const x of node) walk(x); return; }
    // YouTube renders a channel's videos as lockupViewModel now, not
    // videoRenderer, so the video id is looked for on any object
    if (typeof node.videoId === 'string' && node.videoId.length === 11
        && !seen.has(node.videoId)) {
      seen.add(node.videoId);
      let title = '';
      const meta = node.metadata || node.metadataWithCollapseStatus || {};
      const lockup = meta.lockupMetadataViewModel || {};
      const tm = lockup.title || {};
      if (tm.content) title = tm.content;
      else if (tm.runs && tm.runs[0]) title = tm.runs[0].text || '';
      else if (node.title) {
        title = (node.title.runs && node.title.runs[0] && node.title.runs[0].text)
                || node.title.simpleText || '';
      }
      out.push({id: node.videoId, title: title});
    }
    for (const k in node) walk(node[k]);
  };
  walk(d);
  return JSON.stringify(out);
})()
""".replace("__EXTRACT__", YT_EXTRACT_FN)

YT_COMMENTS_JS = r"""
(async () => {
__EXTRACT__
  const clean = s => (s || '').replace(/\u00a0/g, ' ').replace(/[ \t]+/g, ' ').trim();
  const cfg = window.ytcfg || {};
  const key = cfg.get ? cfg.get('INNERTUBE_API_KEY') : '';
  const ver = cfg.get ? cfg.get('INNERTUBE_CLIENT_VERSION') : '';
  const cname = cfg.get ? String(cfg.get('INNERTUBE_CLIENT_NAME') || 'WEB') : 'WEB';

  const textOf = (o) => {
    if (!o) return '';
    if (typeof o === 'string') return clean(o);
    if (o.simpleText) return clean(o.simpleText);
    if (o.runs) return clean(o.runs.map(r => r.text || '').join(''));
    return '';
  };

  const d = YT_EXTRACT() || {};
  if (!d) return JSON.stringify({comments: [], pages: 0,
                                 error: 'ytInitialData not found'});
  // The comment thread's continuation token lives in the engagement panel
  // whose targetId names the comment section. Any other continuation token
  // in the page returns the engagement panels instead of the comments.
  let token = '';
  const findCommand = (node) => {
    if (!node || typeof node !== 'object') return '';
    if (Array.isArray(node)) {
      for (const x of node) { const t = findCommand(x); if (t) return t; }
      return '';
    }
    const cc = node.continuationCommand;
    if (cc && cc.token) return cc.token;
    for (const k in node) { const t = findCommand(node[k]); if (t) return t; }
    return '';
  };
  const panels = d.engagementPanels || [];
  for (const p of panels) {
    const e = p.engagementPanelSectionListRenderer;
    if (e && /comment/i.test(e.targetId || '')) {
      token = findCommand(e.content);
      if (token) break;
    }
  }
  if (!token) token = findCommand(d);
  if (!token) return JSON.stringify({comments: [], pages: 0,
                                     error: 'no continuation token'});

  const comments = [];
  const seen = new Set();
  let pages = 0;
  let nextToken = token;

  while (nextToken && pages < 12) {
    let r;
    try {
      r = await fetch('/youtubei/v1/next?key=' + key, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          context: {client: {clientName: cname, clientVersion: ver, hl: 'en', gl: 'PH'}},
          continuation: nextToken
        })
      });
    } catch (e) {
      return JSON.stringify({comments: comments, pages: pages, error: String(e)});
    }
    if (!r.ok) break;
    const j = await r.json();

    const items = []
      .concat((j.onResponseReceivedActions || []).map(
        a => a.appendContinuationItemsAction && a.appendContinuationItemsAction.continuationItems))
      .concat((j.onResponseReceivedEndpoints || []).map(
        a => (a.appendContinuationItemsAction && a.appendContinuationItemsAction.continuationItems) ||
             (a.reloadContinuationItemsCommand && a.reloadContinuationItemsCommand.continuationItems)))
      .filter(Boolean);
    const flat = [];
    const flatten = (node) => {
      if (!node || typeof node !== 'object') return;
      if (Array.isArray(node)) { for (const x of node) flatten(x); return; }
      flat.push(node);
      for (const k in node) flatten(node[k]);
    };
    flatten(items);

    for (const node of flat) {
      const vm = node.commentViewModel;
      if (vm) {
        const body = textOf(vm.commentText || vm.commentContent);
        const id = vm.commentId || '';
        if (id && !seen.has(id)) {
          seen.add(id);
          comments.push({
            comment_text: body.slice(0, 4000),
            author_name: clean(((vm.author && vm.author.displayName) ||
                                (vm.authorCore && vm.authorCore.displayName) || '')).slice(0, 120),
            timestamp_raw: clean(vm.publishedTime || '').slice(0, 60),
            permalink: id ? location.origin + location.pathname + '?lc=' + id : '',
            is_reply: false, replies_count: '', edited: false, has_translation: false,
          });
        }
      }
      const tr = node.commentThreadRenderer;
      if (tr && tr.comment) {
        const c = tr.comment;
        const body = textOf(c.contentText || c.text);
        const id = c.id || '';
        if (id && !seen.has(id)) {
          seen.add(id);
          comments.push({
            comment_text: body.slice(0, 4000),
            author_name: clean((c.author && c.author.displayName) || '').slice(0, 120),
            timestamp_raw: clean(c.publishedTime || '').slice(0, 60),
            permalink: id ? location.origin + location.pathname + '?lc=' + id : '',
            is_reply: false, replies_count: String(tr.replyCount || 0),
            edited: false, has_translation: false,
          });
        }
      }
    }

    nextToken = findCommand(items);
    pages++;
  }

  const vd = (window.ytInitialPlayerResponse && window.ytInitialPlayerResponse.videoDetails) || {};
  const title = vd.title || (d.videoDetails && d.videoDetails.title) || document.title;

  return JSON.stringify({
    url: location.href,
    title: document.title,
    post: {post_text: clean(title), post_channel: vd.author || '',
           post_views: '', post_date: ''},
    n_comments: comments.length,
    n_threads: comments.length,
    comments: comments,
    pages: pages,
  });
})()
""".replace("__EXTRACT__", YT_EXTRACT_FN)


def discover_youtube_posts(page: str, limit: int = 8) -> list:
    """The channel's videos, read from the page's own data."""
    try:
        v = eval_json(page, YT_DISCOVER_JS, timeout=120)
    except (OrcaError, ValueError):
        return []
    if not isinstance(v, list):
        return []
    out = []
    for item in v:
        vid = item.get("id") if isinstance(item, dict) else None
        if not vid:
            continue
        out.append((f"https://www.youtube.com/watch?v={vid}", item.get("title", "")))
        if len(out) >= limit:
            break
    return out


def capture_youtube_post(page: str, url: str) -> dict:
    """A YouTube video and its comments, read from the page's own data.

    The DOM is used when it has rendered; the public endpoint the page
    itself calls is used when it has not, which is the normal case in a tab
    that is only being driven.
    """
    goto(page, url, settle=4.0)
    for _ in range(8):
        try:
            v = eval_json(page, "typeof window.ytInitialData !== 'undefined' ? 1 : 0")
        except (OrcaError, ValueError):
            v = 0
        if v:
            break
        time.sleep(1.0)

    data = {}
    try:
        v = eval_json(page, YT_COMMENTS_JS, timeout=180)
        if isinstance(v, dict):
            data = v
    except (OrcaError, ValueError) as e:
        data = {"error": str(e)}

    if not data.get("comments"):
        # fall back to the DOM, in case the app did render
        try:
            v = eval_json(page, load_extract_js("extract_youtube.js"))
            if isinstance(v, dict) and v.get("comments"):
                return v
        except (OrcaError, ValueError):
            pass
    return data


def capture_account(page: str, account_url: str, extract_js: str,
                    platform: str = "facebook", limit: int = 6,
                    mode: str = "recent", rounds: int = 10):
    """Collect posts from one account in a single page load.

    Navigating to a post permalink does not work reliably: Facebook serves
    the post without its comment thread, or the home feed instead, for a
    logged-in session. Clicking the permalink on the account's own page
    opens the post with the thread attached, so the posts are clicked where
    they sit instead of being navigated to.

    The feed is virtualized, so the links are taken from the DOM as it
    stands and clicked immediately, before the feed scrolls on.

    Returns a list of (post_url, data) pairs.
    """
    goto(page, account_url, settle=5.0)
    wait_for_content(page, ["followers", "Posts"], timeout=20.0)
    time.sleep(1.0)

    if platform == "facebook":
        open_posts_tab(page, platform)
        time.sleep(1.5)

    seen = set()
    entries = []
    for _ in range(rounds):
        if len(entries) >= limit:
            break
        try:
            items = eval_json(page, post_links_js(platform)) or []
        except OrcaError:
            break

        fresh = []
        for item in items:
            if not isinstance(item, dict):
                continue
            u = item.get("u")
            if not u or u in seen:
                continue
            seen.add(u)
            fresh.append(item)

        for item in fresh:
            if len(entries) >= limit:
                break
            data = capture_one(page, item["u"], extract_js, platform)
            if data:
                data["post_url"] = item["u"]
                entries.append((item["u"], data))

        if len(entries) >= limit:
            break
        scroll_feed(page, platform)
        time.sleep(0.5)

    return entries


def capture_post(page: str, url: str, extract_js: str, platform: str = "facebook",
                 mode: str = "recent"):
    """Open a post, load the whole thread, extract it."""
    # The URL the feed gave us is kept: it is the one that has to be clicked
    # in the fallback. A photo post's feed link is /photo/?fbid=<id>, while
    # the post behind it is /<page>/posts/pfbid..., and the feed only carries
    # the first of the two.
    feed_url = url

    goto(page, url, settle=3.0)
    if platform == "facebook":
        real = resolve_view_post(page)
        if real and real != url:
            goto(page, real, settle=3.0)
            url = real
    n_loaded, scrolled = load_thread(page, platform, wait_rounds=6)

    if platform == "facebook" and n_loaded == 0:
        # The thread did not render. Facebook will not always route a direct
        # permalink for a logged-in session - it serves the post without its
        # comments, or the home feed instead - but clicking the permalink on
        # the account's own page opens the post with the thread attached.
        slug = page_slug_from_url(feed_url) or page_slug_from_url(url)
        if slug:
            goto(page, f"https://www.facebook.com/{slug}", settle=5.0)
            wait_for_content(page, ["followers", "Posts"], timeout=20.0)
            time.sleep(1.5)
            state = click_permalink(page, feed_url)
            if state == "clicked":
                time.sleep(2.5)
                n_loaded, scrolled = load_thread(page, platform)
                if n_loaded == 0:
                    # the click opened a photo preview, not the post
                    real2 = resolve_view_post(page)
                    if real2:
                        click_permalink(page, real2)
                        time.sleep(2.0)
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
    ap.add_argument("--mode", default="recent", choices=["recent", "invites"],
                    help="recent = the most recent posts; "
                         "invites = the posts that invite citizen requests")
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
    if args.mode == "invites" and args.platform == "facebook":
        urls = find_inviting_posts(page, limit=args.posts)
    else:
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
    notes = args.notes or ""
    if args.mode and args.mode != "recent":
        notes = f"{notes} stratum={args.mode}".strip()
    snap = build_snapshot(args.source_page, args.source_page_name, args.agency_id,
                          args.platform, entries, notes=notes)
    path = write_snapshot(snap)
    n = sum(p["n_comments"] for p in snap["posts"])
    print(f"\nSNAPSHOT -> {path}")
    print(f"  {len(snap['posts'])} post(s), {n} comment(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
