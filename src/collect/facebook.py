"""
facebook.py — Stage 1. Collect public comments from a Facebook post permalink.

Reads the publicly visible HTML/DOM of a post page with a headless browser and
records the comment thread verbatim. No API key, no access token, no account
credentials, no login.

Facebook changes its markup often, so the extractor is built defensively:

  * several candidate selectors per field, tried in order
  * a generic fallback that takes the deepest text block of a comment node
  * `--dump-dom` saves the rendered HTML so selectors can be fixed offline
    against a saved page instead of by re-scraping

The output is an immutable raw snapshot. Cleaning is reproducible from it.

Usage
-----
    # one permalink
    python src/collect/facebook.py \\
        --post-url https://www.facebook.com/SomeAgency/posts/123456 \\
        --source-page some_agency

    # every recent post on a page
    python src/collect/facebook.py \\
        --page-url https://www.facebook.com/SomeAgency \\
        --source-page some_agency \\
        --posts 8

    # debug: save the rendered DOM and stop
    python src/collect/facebook.py \\
        --post-url ... --source-page some_agency --dump-dom
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RAW_ROOT = os.path.join(ROOT, "data", "raw", "facebook")
LOG_PATH = os.path.join(ROOT, "data", "provenance", "collection_log.csv")

# --- politeness / rate behaviour ------------------------------------------
DEFAULT_DELAY = 3.0          # seconds between page loads
MAX_SCROLLS = 40             # scroll attempts per post before giving up
SCROLL_PAUSE = 1.2           # seconds between scrolls
PAGE_TIMEOUT_MS = 45000

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

# --- selectors --------------------------------------------------------------
# Each field tries these in order. The first that matches wins.
COMMENT_CONTAINER_SELECTORS = [
    'div[role="article"][aria-label*="Comment"]',
    'div[role="article"]:has(div[data-testid="comment"])',
    'div[aria-label="Comment"]',
    'div[data-testid="comment"]',
    'li div[role="article"]',
    'div[role="article"]',
]

COMMENT_BODY_SELECTORS = [
    'div[dir="auto"]',
    'span[dir="auto"]',
    '[data-testid="comment-content"]',
]

AUTHOR_SELECTORS = [
    'h3 a',
    'h2 a',
    'a[role="link"] strong',
    'a[role="link"]',
    'strong a',
]

TIMESTAMP_SELECTORS = [
    'abbr',
    'span[data-utime]',
    'a[aria-label*="202"]',
    'span[data-testid="timestamp"]',
]

# A post permalink on the page
POST_LINK_RE = re.compile(r"https?://(?:www\.|m\.)?facebook\.com/[^\s\"']+/posts/\d+")
PERMALINK_RE = re.compile(r"https?://(?:www\.|m\.)?facebook\.com/[^\s\"']+")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_id(source_page: str) -> str:
    return f"fb_{source_page}_{datetime.now().strftime('%Y-%m-%dT%H-%M')}"


def write_snapshot(source_page: str, rid: str, payload: dict) -> str:
    d = os.path.join(RAW_ROOT, source_page)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, f"{rid}.json")
    with io.open(path, "w", encoding="utf-8", newline="") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return path


def append_log(row: dict) -> None:
    """Append one run to data/provenance/collection_log.csv."""
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    fields = ["run_id", "platform", "source_page", "collection_method", "tool", "version",
              "user_agent", "delay_seconds", "post_ids_collected", "comments_collected",
              "collected_at", "raw_snapshot_id", "notes"]
    new = not os.path.exists(LOG_PATH)
    with io.open(LOG_PATH, "a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow({f: row.get(f, "") for f in fields})


def first_text(node, selectors) -> str:
    """Return the text of the first selector that matches."""
    for sel in selectors:
        try:
            found = node.query_selector(sel)
        except Exception:
            found = None
        if found:
            try:
                txt = (found.inner_text() or "").strip()
            except Exception:
                txt = ""
            if txt:
                return txt
    return ""


def deepest_text(node) -> str:
    """Fallback: the longest text of the deepest dir=auto descendant, else the
    node's own text minus its header."""
    best = ""
    try:
        for el in node.query_selector_all('div[dir="auto"], span[dir="auto"]'):
            t = (el.inner_text() or "").strip()
            if len(t) > len(best):
                best = t
    except Exception:
        pass
    if best:
        return best
    try:
        return (node.inner_text() or "").strip()
    except Exception:
        return ""


def extract_comments(page) -> list:
    """Pull the comment thread out of a rendered post page."""
    comments = []
    seen = set()

    for sel in COMMENT_CONTAINER_SELECTORS:
        try:
            nodes = page.query_selector_all(sel)
        except Exception:
            nodes = []
        if not nodes:
            continue

        for node in nodes:
            try:
                body = first_text(node, COMMENT_BODY_SELECTORS) or deepest_text(node)
            except Exception:
                continue
            if not body or len(body) < 2:
                continue

            # a comment is not its own author name or timestamp
            author = first_text(node, AUTHOR_SELECTORS)
            timestamp = first_text(node, TIMESTAMP_SELECTORS)

            key = (body[:200], author[:80])
            if key in seen:
                continue
            seen.add(key)

            comments.append({
                "comment_text": body,
                "author_name": author,
                "timestamp_raw": timestamp,
                "is_reply": False,
            })
        if comments:
            break

    return comments


def scroll_thread(page, max_scrolls: int = MAX_SCROLLS, pause: float = SCROLL_PAUSE) -> int:
    """Scroll the comment section to pull more of the thread into the DOM."""
    scrolls = 0
    stable = 0
    last_count = -1
    for _ in range(max_scrolls):
        try:
            page.mouse.wheel(0, 4000)
        except Exception:
            break
        time.sleep(pause)
        scrolls += 1
        try:
            n = len(page.query_selector_all(COMMENT_CONTAINER_SELECTORS[0]))
        except Exception:
            n = 0
        if n == last_count and n > 0:
            stable += 1
            if stable >= 3:
                break
        else:
            stable = 0
        last_count = n
    return scrolls


def find_post_links(page, limit: int) -> list:
    """Collect post permalinks from a page."""
    links = []
    seen = set()
    try:
        anchors = page.query_selector_all("a[href]")
    except Exception:
        anchors = []
    for a in anchors:
        try:
            href = a.get_attribute("href") or ""
        except Exception:
            continue
        m = POST_LINK_RE.search(href)
        if not m:
            continue
        url = m.group(0).split("?")[0]
        if url in seen:
            continue
        seen.add(url)
        links.append(url)
        if len(links) >= limit:
            break
    return links


def extract_post_meta(page) -> dict:
    """The post's own caption, permalink and timestamp."""
    caption = ""
    for sel in ['div[role="article"] div[dir="auto"]', 'div[dir="auto"]']:
        try:
            el = page.query_selector(sel)
        except Exception:
            el = None
        if el:
            caption = (el.inner_text() or "").strip()
            if caption:
                break
    permalink = ""
    try:
        el = page.query_selector('link[rel="canonical"]')
        if el:
            permalink = el.get_attribute("href") or ""
    except Exception:
        pass
    if not permalink:
        try:
            permalink = page.url
        except Exception:
            pass
    posted = ""
    for sel in TIMESTAMP_SELECTORS:
        try:
            el = page.query_selector(sel)
        except Exception:
            el = None
        if el:
            posted = (el.inner_text() or "").strip()
            break
    return {"post_text": caption, "post_url": permalink, "post_date_raw": posted}


# ---------------------------------------------------------------------------
# The scrape
# ---------------------------------------------------------------------------

def _candidate_browser_paths() -> list:
    """Existing Playwright chromium builds on this machine, newest first.

    `playwright install` downloads a specific build for the installed
    Playwright version. If that build is missing but an older or newer
    chromium is already present, using it beats refusing to run.
    """
    roots = []
    env_root = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env_root:
        roots.append(env_root)
    if sys.platform.startswith("win"):
        roots.append(os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright"))
    elif sys.platform == "darwin":
        roots.append(os.path.join(os.path.expanduser("~"), "Library", "Caches", "ms-playwright"))
    else:
        roots.append(os.path.join(os.path.expanduser("~"), ".cache", "ms-playwright"))

    found = []
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root), reverse=True):
            if not name.startswith("chromium-"):
                continue
            for rel in (("chrome-win64", "chrome.exe"),
                        ("chrome-win", "chrome.exe"),
                        ("chrome-mac", "Chromium.app/Contents/MacOS/Chromium"),
                        ("chrome-linux", "chrome")):
                p = os.path.join(root, name, *rel)
                if os.path.exists(p):
                    found.append(p)
                    break
    return found


def launch_browser(pw, headless: bool = True):
    """Launch chromium, falling back to an already-installed build if the
    exact build this Playwright expects is not present."""
    override = os.environ.get("CHROMIUM_PATH")
    if override and os.path.exists(override):
        return pw.chromium.launch(headless=headless, executable_path=override)

    try:
        return pw.chromium.launch(headless=headless)
    except Exception as first:
        for path in _candidate_browser_paths():
            try:
                print(f"  using installed browser: {path}")
                return pw.chromium.launch(headless=headless, executable_path=path)
            except Exception:
                continue
        raise first


def scrape(post_url: str, source_page: str, delay: float, dump_dom: bool,
           headless: bool = True) -> dict:
    """Scrape one post permalink. Returns the snapshot payload."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("ERROR: playwright is not installed.")
        print("       pip install playwright && playwright install chromium")
        return {}

    comments = []
    post_meta = {}
    scrolls = 0
    error = ""

    with sync_playwright() as pw:
        browser = launch_browser(pw, headless=headless)
        context = browser.new_context(user_agent=USER_AGENT,
                                      viewport={"width": 1280, "height": 2000},
                                      locale="en_PH")
        page = context.new_page()
        try:
            page.goto(post_url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
            time.sleep(2.0)
            post_meta = extract_post_meta(page)
            scrolls = scroll_thread(page)
            comments = extract_comments(page)
            if dump_dom:
                d = os.path.join(RAW_ROOT, source_page)
                os.makedirs(d, exist_ok=True)
                html_path = os.path.join(d, f"{run_id(source_page)}_dom.html")
                with io.open(html_path, "w", encoding="utf-8") as fh:
                    fh.write(page.content())
                print(f"  DOM saved -> {html_path}")
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            print(f"  ERROR loading {post_url}: {error}")
        finally:
            context.close()
            browser.close()

    return {
        "run_id": run_id(source_page),
        "source_page": source_page,
        "platform": "facebook",
        "collection_method": "dom_headless",
        "collected_at": now_iso(),
        "post_url": post_url,
        "post": post_meta,
        "scrolls": scrolls,
        "n_comments": len(comments),
        "comments": comments,
        "error": error,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Stage 1 - collect public Facebook comments")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--post-url", help="a single post permalink")
    g.add_argument("--page-url", help="a page URL; recent posts are discovered from it")
    ap.add_argument("--source-page", required=True, help="slug for this source")
    ap.add_argument("--posts", type=int, default=8, help="how many posts to take from a page")
    ap.add_argument("--delay", type=float, default=DEFAULT_DELAY, help="seconds between posts")
    ap.add_argument("--dump-dom", action="store_true", help="save the rendered HTML and stop")
    ap.add_argument("--headed", action="store_true", help="show the browser")
    ap.add_argument("--no-log", action="store_true", help="do not append to the collection log")
    args = ap.parse_args(argv)

    rid = run_id(args.source_page)
    urls = []

    if args.post_url:
        urls = [args.post_url]
    else:
        # discover post links from the page first
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("ERROR: playwright is not installed.")
            return 1
        with sync_playwright() as pw:
            browser = launch_browser(pw, headless=not args.headed)
            ctx = browser.new_context(user_agent=USER_AGENT, locale="en_PH")
            page = ctx.new_page()
            try:
                page.goto(args.page_url, timeout=PAGE_TIMEOUT_MS, wait_until="domcontentloaded")
                time.sleep(2.0)
                urls = find_post_links(page, args.posts)
            except Exception as e:
                print(f"  ERROR loading {args.page_url}: {e}")
            finally:
                ctx.close()
                browser.close()
        print(f"  found {len(urls)} post link(s)")

    if not urls:
        print("No post URLs to scrape.")
        return 1

    snapshots = []
    for i, url in enumerate(urls, 1):
        print(f"[{i}/{len(urls)}] {url}")
        payload = scrape(url, args.source_page, args.delay, args.dump_dom,
                         headless=not args.headed)
        if payload:
            snapshots.append(payload)
            print(f"  {payload.get('n_comments', 0)} comment(s), "
                  f"{payload.get('scrolls', 0)} scroll(s)")
        if i < len(urls):
            time.sleep(args.delay)

    total = sum(s.get("n_comments", 0) for s in snapshots)
    print(f"\ntotal comments collected: {total}")

    path = write_snapshot(args.source_page, rid, {
        "run_id": rid,
        "source_page": args.source_page,
        "platform": "facebook",
        "collection_method": "dom_headless",
        "collected_at": now_iso(),
        "tool": "playwright",
        "user_agent": USER_AGENT,
        "delay_seconds": args.delay,
        "n_posts": len(snapshots),
        "n_comments": total,
        "snapshots": snapshots,
    })
    print(f"raw snapshot -> {path}")

    if not args.no_log:
        append_log({
            "run_id": rid, "platform": "facebook", "source_page": args.source_page,
            "collection_method": "dom_headless", "tool": "playwright", "version": "1.x",
            "user_agent": USER_AGENT, "delay_seconds": args.delay,
            "post_ids_collected": len(snapshots), "comments_collected": total,
            "collected_at": now_iso(), "raw_snapshot_id": rid,
            "notes": "; ".join(s.get("error", "") for s in snapshots if s.get("error")),
        })
        print(f"logged -> {LOG_PATH}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
