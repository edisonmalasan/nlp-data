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
        self.fh.write(line + "\n")
        self.fh.flush()

    def close(self):
        try:
            self.fh.close()
        except Exception:
            pass


class Tee:
    """Captures what the collector prints and writes it to the worker's log."""

    def __init__(self, log):
        self.log = log
        self.buf = ""

    def write(self, s):
        self.buf += s
        while "\n" in self.buf:
            line, self.buf = self.buf.split("\n", 1)
            if line.strip():
                self.log(line)
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


def progress_path(platform: str) -> str:
    os.makedirs(PROGRESS_DIR, exist_ok=True)
    return os.path.join(PROGRESS_DIR, f"{platform}.json")


def load_progress(platform: str) -> dict:
    p = progress_path(platform)
    if not os.path.exists(p):
        return {}
    try:
        return json.load(io.open(p, encoding="utf-8"))
    except Exception:
        return {}


def save_progress(platform: str, data: dict):
    p = progress_path(platform)
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

    log = WorkerLog(os.path.join(LOG_DIR, f"{args.platform}.log"))
    log(f"=== worker: {args.platform} on tab {args.tab}, {args.posts} posts, "
        f"mode={args.mode} ===")

    try:
        tabs = ensure_tabs(args.tab + 1)
        tab = ob.pick_tab(tabs, index=args.tab)
        page = tab["browserPageId"]
        log(f"tab [{args.tab}] {page}  {tab.get('url')}")

        registry = [r for r in run_all.read_registry() if r["platform"] == args.platform]
        progress = load_progress(args.platform)
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
            if snaps and not os.environ.get("FORCE"):
                log(f"[{i}/{len(registry)}] {key}: already collected, skipping")
                continue
            if run_all.existing_snapshots(row["platform"], row["source_page"],
                                          args.mode):
                log(f"[{i}/{len(registry)}] {key}: the last attempt was empty, retrying")

            log(f"[{i}/{len(registry)}] {key}  {row.get('official_account_url', '')}")
            tee = Tee(log)
            try:
                # the collector prints as it goes; capture that into the log
                with contextlib.redirect_stdout(tee):
                    n_posts, n_comments, err = run_all.run_one(
                        page, row, args.posts, notes, args.mode)
            except Exception as e:
                n_posts, n_comments, err = 0, 0, f"{type(e).__name__}: {e}"
                log(f"  FAILED: {err}")
                traceback.print_exc()
            if tee.buf.strip():
                log(tee.buf.strip())

            prev = progress.get(key, {})
            progress[key] = {
                "posts": prev.get("posts", 0) + n_posts,
                "comments": prev.get("comments", 0) + n_comments,
                "last_error": err,
                "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            save_progress(args.platform, progress)
            if err:
                log(f"  error: {err}")
            else:
                done += 1
                log(f"  ok: {n_posts} post(s), {n_comments} comment(s)")
            time.sleep(args.pause)

        log(f"=== {args.platform} worker finished: {done} account(s) collected ===")
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
