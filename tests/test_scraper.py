"""
test_scraper.py — assertions for the Stage 1 Facebook extractor.

    python tests/run_all.py

Runs against a saved HTML fixture that mimics Facebook's comment markup, so the
extraction logic is verified without touching the live site. When Facebook
changes its markup, save a fresh page with `--dump-dom` and update the fixture
rather than re-scraping in a loop.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fb_fixture.html")


def run() -> list:
    failures = []

    def check(name, got, want):
        if got != want:
            failures.append(f"{name}: got {got!r} want {want!r}")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return ["playwright is not installed"]

    from collect.facebook import (extract_comments, extract_post_meta,
                                  find_post_links, launch_browser)

    if not os.path.exists(FIXTURE):
        return [f"missing fixture: {FIXTURE}"]

    with sync_playwright() as pw:
        browser = launch_browser(pw)
        try:
            page = browser.new_page()
            page.goto("file:///" + FIXTURE.replace("\\", "/"))
            page.wait_for_load_state("domcontentloaded")

            comments = extract_comments(page)
            texts = [c["comment_text"] for c in comments]

            check("found the 4 comments", len(comments), 4)
            if len(texts) >= 4:
                check("comment 1 text", texts[0],
                      "Please repair the damaged road in our barangay.")
                check("comment 2 text", texts[1],
                      "Ang pangit ng kalsada namin. Please fix it soon.")
                check("comment 3 text", texts[2], "Same, please fix ours too.")
                check("comment 4 text", texts[3],
                      "Salamat sa mga doctor, mabuting trabaho po!")
                check("author 1", comments[0]["author_name"], "Juan Dela Cruz")
                check("author 4", comments[3]["author_name"], "Ana Reyes")
                check("timestamp 1", comments[0]["timestamp_raw"], "2 hours ago")
            # the post's own caption must not be extracted as a comment
            check("post caption is not a comment", "SYABAS" in " ".join(texts), False)

            meta = extract_post_meta(page)
            check("post caption", meta["post_text"][:6], "SYABAS")
            check("post url", meta["post_url"],
                  "https://www.facebook.com/PAGASA/posts/1234567890")
            check("post date", meta["post_date_raw"], "October 20, 2026")

            page2 = browser.new_page()
            page2.set_content(
                '<a href="https://www.facebook.com/PAGASA/posts/111">a</a>'
                '<a href="https://www.facebook.com/PAGASA/posts/222?__cft__=x">b</a>'
                '<a href="https://www.facebook.com/PAGASA/posts/111">dup</a>'
                '<a href="https://www.facebook.com/PAGASA/other">not a post</a>'
            )
            links = find_post_links(page2, 10)
            check("finds 2 unique post links", len(links), 2)
            check("strips the query string", links[1],
                  "https://www.facebook.com/PAGASA/posts/222")
        finally:
            browser.close()

    return failures
