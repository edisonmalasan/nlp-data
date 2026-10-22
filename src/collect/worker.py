"""
worker.py — one collection worker, bound to one browser tab.

The browser can drive several tabs at once: `goto` and `eval` take an
explicit --page, so a worker that stays on its own tab does not disturb
another worker. That is what makes the collection parallel - one worker per
platform, each with its own tab.

Each worker owns:

  * its own tab, which it never switches away from
  * its own progress file, so two workers cannot clobber each other's state
  * its own log file, so a run can be diagnosed after the fact

Usage
-----
    python src/collect/worker.py --platform facebook --tab 0 --posts 5
    python src/collect/worker.py --platform x       --tab 2 --posts 5
    python src/collect/worker.py --platform reddit  --tab 3 --posts 5
    python src/collect/worker.py --platform facebook --tab 0 --mode invites

The worker is resumable: an account that already has a snapshot for the
stratum is skipped, so a crashed worker can simply be started again.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import subprocess
import sys
import time
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import orca_browser as ob
import run_all

PROGRESS_DIR = os.path.join(ROOT, "data", "provenance", "progress")
LOG_DIR = os.path.join(ROOT, "data", "provenance", "logs")


class WorkerLog:
    """Writes to stdout and to a file, and flushes.

    The background shell does not always capture a python process's stdout,
    so the file is the record of what happened.
    """

    def __init__(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self.fh = io.open(path, "a", encoding="utf-8", newline="")

    def __call__(self, msg: str = ""):
        line = f"[{time.strftime('%H:%M:%S')}] {msg}"
        try:
            print(line, flush=True)
        except Exception:
            pass
        self.write_line(line)

    def write_line(self, line: str):
        """Write a line to the log file, with no timestamp added."""
        try:
            self.fh.write(line + "\n")
            self.fh.flush()
        except Exception:
            pass

    def close(self):
        try:
            self.fh.close()
        except Exception:
            pass


class Tee:
    """Captures what the collector prints and writes it to the worker's log.

    It writes to the log file directly. Calling the logger would recurse:
    the logger prints to stdout, stdout is the tee, and the tee calls the
    logger again, so every line would be written once per level of the
    recursion.
    """

    def __init__(self, log):
        self.log = log
        self.buf = ""

    def write(self, s):
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            if line.strip():
                self.log.write_line(line)
        return len(s)

    def flush(self):
        pass

    def isatty(self):
        return False


def ensure_tabs(n: int):
    """Make sure there are at least n tabs, and return them."""
    tabs = ob.list_tabs()
    while len(tabs) < n:
        try:
            ob.orca("tab", "create")
        except ob.OrcaError as e:
            raise SystemExit(f"could not create a tab: {e}")
        time.sleep(1.5)
        tabs = ob.list_tabs()
    return tabs


def progress_path(platform: str, mode: str = "recent") -> str:
    """One progress file per platform AND stratum.

    Two workers can be on the same platform at once - the recent-posts
    stratum and the request-inviting stratum - and they must not write to
    the same file.
    """
    os.makedirs(PROGRESS_DIR, exist_ok=True)
    suffix = "" if mode in ("recent", "") else f"_{mode}"
    return os.path.join(PROGRESS_DIR, f"{platform}{suffix}.json")


def load_progress(platform: str, mode: str = "recent") -> dict:
    p = progress_path(platform, mode)
    if not os.path.exists(p):
        return {}
    try:
        return json.load(io.open(p, encoding="utf-8"))
    except Exception:
        return {}


def save_progress(platform: str, data: dict, mode: str = "recent"):
    p = progress_path(platform, mode)
    tmp = p + ".tmp"
    with io.open(tmp, "w", encoding="utf-8", newline="") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)
    os.replace(tmp, p)


def merge_progress() -> dict:
    """Fold the per-worker progress files into the collection progress file."""
    merged = {}
    if os.path.isdir(PROGRESS_DIR):
        for f in sorted(os.listdir(PROGRESS_DIR)):
            if not f.endswith(".json"):
                continue
            try:
                d = json.load(io.open(os.path.join(PROGRESS_DIR, f), encoding="utf-8"))
            except Exception:
                continue
            for k, v in d.items():
                merged[k] = v
    out = os.path.join(ROOT, "data", "provenance", "collection_progress.json")
    with io.open(out, "w", encoding="utf-8", newline="") as fh:
        json.dump(merged, fh, indent=2, ensure_ascii=False)
    return merged


def main(argv=None) -> int:
    import browser_lock
    if not browser_lock.take("this worker", log=print):
        return 2
    try:
        return _run(argv)
    finally:
        browser_lock.release()


def _run(argv=None) -> int:
    ap = argparse.ArgumentParser(description="One collection worker, one tab")
    ap.add_argument("--platform", required=True,
                    choices=["facebook", "youtube", "x", "reddit"])
    ap.add_argument("--tab", type=int, required=True, help="the tab index this worker owns")
    ap.add_argument("--posts", type=int, default=5)
    ap.add_argument("--mode", default="recent", choices=["recent", "invites"])
    ap.add_argument("--pause", type=float, default=8.0,
                    help="seconds between accounts")
    ap.add_argument("--notes", default="")
    args = ap.parse_args(argv)

    suffix = "" if args.mode in ("recent", "") else f"_{args.mode}"
    log = WorkerLog(os.path.join(LOG_DIR, f"{args.platform}{suffix}.log"))
    heartbeat = os.path.join(PROGRESS_DIR, f"heartbeat_{args.platform}{suffix}.json")

    def beat(state, **extra):
        """The worker's state, written outside the log.

        A worker can die without a word - the browser helper can take the
        process down with it - and then the log simply stops. The heartbeat
        is written every time the state changes, so a dead worker is
        visible instead of looking like a slow one.
        """
        try:
            with io.open(heartbeat, "w", encoding="utf-8", newline="") as fh:
                json.dump({"platform": args.platform, "tab": args.tab,
                           "mode": args.mode, "state": state,
                           "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                           **extra}, fh, indent=2, ensure_ascii=False)
        except Exception:
            pass

def fresh_tab(log):
    """A brand new tab, because a used one stops serving the feed.

    A Facebook page serves its full recent feed only on the FIRST load in a
    tab. Every load after that in the same tab renders the page header and
    one or two posts, and neither scrolling nor a reload brings the rest
    back. That is measurable: on the pages below, a tab that had been used
    served 2 to 6 post permalinks, and a tab created for the same page served
    the full 12.

    | page                    | used tab | fresh tab |
    |-------------------------|----------|-----------|
    | pnagovph                |    2     |    12     |
    | sugarregulatoryadmin    |    2     |    12     |
    | nncofficial             |    6     |    12     |
    | civildefensePH          |    3     |    12     |

    So each account is collected in a tab created for it, and the tab is
    closed afterwards. Forty-seven extra tabs per pass is cheap; the posts
    are the point.
    """
    try:
        subprocess.run(["orca", "tab", "create", "--url", "about:blank"],
                       capture_output=True, text=True, timeout=90)
    except (OSError, subprocess.SubprocessError) as e:
        log(f"  could not create a tab: {e}")
        return None
    time.sleep(2.0)
    tabs = ob.list_tabs()
    return tabs[-1]["browserPageId"] if tabs else None


def close_tab(page, log):
    try:
        subprocess.run(["orca", "tab", "close", "--page", page],
                       capture_output=True, text=True, timeout=90)
    except (OSError, subprocess.SubprocessError):
        pass


    beat("starting")
    log(f"=== worker: {args.platform} on tab {args.tab}, {args.posts} posts, "
        f"mode={args.mode} ===")

    try:
        tabs = ensure_tabs(args.tab + 1)
        tab = ob.pick_tab(tabs, index=args.tab)
        page = tab["browserPageId"]
        log(f"tab [{args.tab}] {page}  {tab.get('url')}")

        registry = [r for r in run_all.read_registry() if r["platform"] == args.platform]
        progress = load_progress(args.platform, args.mode)
        log(f"{len(registry)} registered {args.platform} accounts")

        notes = args.notes or (f"collection run via orca built-in browser, "
                               f"{args.posts} posts/account")
        if args.mode != "recent":
            notes = f"{notes} stratum={args.mode}"

        done = 0
        for i, row in enumerate(registry, 1):
            key = f"{row['platform']}/{row['source_page']}"
            snaps = run_all.usable_snapshots(row["platform"], row["source_page"],
                                            args.mode)
            have = run_all.collected_posts(row["platform"], row["source_page"],
                                           args.mode)
            if snaps and have >= args.posts and not os.environ.get("FORCE"):
                log(f"[{i}/{len(registry)}] {key}: already collected "
                    f"({have} post(s)), skipping")
                continue
            if not snaps and have:
                log(f"[{i}/{len(registry)}] {key}: the last attempt was empty, retrying")
            elif have:
                log(f"[{i}/{len(registry)}] {key}: topping up ({have} of {args.posts} posts)")

            log(f"[{i}/{len(registry)}] {key}  {row.get('official_account_url', '')}")
            tee = Tee(log)
            beat("collecting", source_page=row["source_page"])
            # a tab of its own, because the first load in a tab is the only
            # one that serves the page's full recent feed
            acct_page = fresh_tab(log) or page
            try:
                # the collector prints as it goes; capture that into the log
                with contextlib.redirect_stdout(tee):
                    n_posts, n_comments, err = run_all.run_one(
                        acct_page, row, args.posts, notes, args.mode)
            except BaseException as e:
                # a hard exit - the browser helper can take the process down
                # with it - must not stop the rest of the run
                n_posts, n_comments, err = 0, 0, f"{type(e).__name__}: {e}"
                log(f"  FAILED: {err}")
                traceback.print_exc()
            finally:
                if acct_page != page:
                    close_tab(acct_page, log)
            if tee.buf.strip():
                log(tee.buf.strip())

            prev = progress.get(key, {})
            progress[key] = {
                "posts": prev.get("posts", 0) + n_posts,
                "comments": prev.get("comments", 0) + n_comments,
                "last_error": err,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            save_progress(args.platform, progress, args.mode)
            if err:
                log(f"  error: {err}")
            else:
                done += 1
                log(f"  ok: {n_posts} post(s), {n_comments} comment(s)")
            beat("collected" if not err else "failed",
                 source_page=row["source_page"], accounts_done=done)
            time.sleep(args.pause)

        log(f"=== {args.platform} worker finished: {done} account(s) collected ===")
        beat("finished", accounts_done=done)
        return 0
    except SystemExit:
        raise
    except Exception as e:
        log(f"worker crashed: {type(e).__name__}: {e}")
        traceback.print_exc()
        return 1
    finally:
        merge_progress()
        log.close()


if __name__ == "__main__":
    sys.exit(main())
