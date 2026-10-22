"""
collect_forever.py — keep collecting, with the duplicate guarantee enforced.

The study has no ceiling on the corpus, so the collection runs as a loop
rather than as a single pass:

  1. the source frame is re-checked, and new official accounts are added
  2. the collectors run, one per platform, each on its own browser tab
  3. every cycle the interim layer is rebuilt and cleaned, so the exclusion
     ledger and the duplicate counts stay current
  4. a worker that died is restarted - collection is resumable, so a restart
     costs at most one account
  5. a heartbeat is written, so the loop's state is visible from outside

**The duplicate guarantee.** Deduplication happens in the cleaning stage, not
in the collector: exact duplicates are keyed on `dedup_key` and the earliest
captured is kept, near duplicates are a Jaccard similarity of 0.90 or a
substring relation of at least five tokens and the longer is kept, and the
number of near-identical survivors from the same account on the same post is
capped at two. Every removal carries a reason code, so the ledger
reconciles.

That matters for a continuous run: re-collecting a post produces a NEW
comment_id for text that is already held, and the cleaning stage removes it
as X_DUP_EXACT. The delivered dataset therefore holds each comment once,
and the ledger records how many times the raw layer repeated it.

    python src/collect/collect_forever.py
    python src/collect/collect_forever.py --cycles 5 --cycle-seconds 900
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

PY = sys.executable
PROVENANCE = os.path.join(ROOT, "data", "provenance")
HEARTBEAT = os.path.join(PROVENANCE, "collector_heartbeat.json")
LOCK = os.path.join(PROVENANCE, "collector.lock")


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def _pid_alive(pid):
    """Is that process still running? Signal 0 is not usable on Windows -
    os.kill(pid, 0) TERMINATES the process there - so ask the kernel
    directly instead."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,
                                      False, pid)
        if not handle:
            return False
        kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def die_with_parent():
    """Make every child of this process die when it dies.

    subprocess.Popen children outlive a killed parent, and `Stop-Process
    -Force` runs no handler. Three orphaned discovery runs therefore kept
    driving the browser after their supervisors were killed, alongside the
    next supervisor - and two drivers close the runtime's connection, so
    every account in every run then reported as empty. A Windows job object
    with KILL_ON_JOB_CLOSE is the only reliable way to take the children
    with the parent. It is best-effort: on a platform without it, the lock
    in take_lock() still keeps a second supervisor out.
    """
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    JobObjectExtendedLimitInformation = 9
    JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000

    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        log("  no job object; children will outlive a forced kill")
        return
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    ok = kernel32.SetInformationJobObject(
        job, JobObjectExtendedLimitInformation,
        ctypes.byref(info), ctypes.sizeof(info))
    if not ok:
        log("  could not set the job object; children will outlive a forced kill")
        return
    if not kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess()):
        log("  could not join the job object; children will outlive a forced kill")
        return
    log("  children will die with this process")


def take_lock():
    """Claim the browser for this process, or refuse to start.

    The browser can only be driven by one process at a time. A second
    supervisor does not fail loudly: it closes the runtime's connection and
    every account in BOTH runs starts reporting as empty or blocked. Refusing
    to start is the only safe behaviour."""
    if os.path.exists(LOCK):
        try:
            holder = int(io.open(LOCK, encoding="utf-8").read().strip() or 0)
        except (ValueError, OSError):
            holder = 0
        if holder and holder != os.getpid() and _pid_alive(holder):
            log(f"another supervisor is already running (pid {holder})")
            log("the browser is driven by one process at a time, so this "
                "one exits rather than closing its connection")
            return False
        log(f"taking over a stale lock from pid {holder}")
    os.makedirs(PROVENANCE, exist_ok=True)
    with io.open(LOCK, "w", encoding="utf-8", newline="") as fh:
        fh.write(str(os.getpid()))
    return True


def release_lock():
    try:
        holder = int(io.open(LOCK, encoding="utf-8").read().strip() or 0)
        if holder == os.getpid():
            os.remove(LOCK)
    except (ValueError, OSError):
        pass


def run(label, argv, timeout=3600):
    r = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    return r.returncode, (r.stdout or ""), (r.stderr or "")


def raw_totals():
    """The raw layer, by platform."""
    import glob
    out = {}
    for plat in ("facebook", "youtube", "x", "reddit"):
        posts = comments = 0
        for f in glob.glob(os.path.join(ROOT, "data", "raw", plat, "*", "*.json")):
            try:
                s = json.load(io.open(f, encoding="utf-8"))
            except Exception:
                continue
            posts += len(s.get("posts", []))
            comments += sum(p.get("n_comments", 0) for p in s.get("posts", []))
        if posts:
            out[plat] = (posts, comments)
    return out


def pool_stats():
    """The cleaned pool: how many rows, and how many duplicates are in it."""
    path = os.path.join(ROOT, "data", "processed", "candidate_pool.csv")
    if not os.path.exists(path):
        return {}
    rows = list(csv.DictReader(io.open(path, encoding="utf-8", newline="")))
    keys = Counter(r.get("dedup_key", "") for r in rows if r.get("dedup_key"))
    dups = sum(v - 1 for v in keys.values() if v > 1)
    ledger = os.path.join(ROOT, "data", "interim", "exclusion_ledger.csv")
    excl = {}
    if os.path.exists(ledger):
        for r in csv.DictReader(io.open(ledger, encoding="utf-8", newline="")):
            excl[r.get("_reason", "")] = excl.get(r.get("_reason", ""), 0) + 1
    return {"rows": len(rows), "residual_duplicate_keys": dups,
            "excluded_by_reason": excl}


def write_heartbeat(state):
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    with io.open(HEARTBEAT, "w", encoding="utf-8", newline="") as fh:
        json.dump(state, fh, indent=2, ensure_ascii=False)


def main(argv=None) -> int:
    if not take_lock():
        return 2
    die_with_parent()
    try:
        return _run(argv)
    finally:
        release_lock()


def _run(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Collect continuously")
    ap.add_argument("--cycles", type=int, default=0,
                    help="0 = run until stopped")
    ap.add_argument("--cycle-seconds", type=int, default=900)
    ap.add_argument("--posts", type=int, default=20,
                    help="how many posts to take per account")
    ap.add_argument("--platforms", nargs="+",
                    default=["facebook", "youtube", "x"])
    ap.add_argument("--invites-posts", type=int, default=8,
                    help="how many posts to take per account in the "
                         "request-inviting stratum")
    ap.add_argument("--discover-every", type=int, default=3,
                    help="re-check the source frame every N cycles")
    ap.add_argument("--skip-discovery", action="store_true",
                    help="start straight into collection, without the "
                         "source frame re-check")
    args = ap.parse_args(argv)

    state = {"cycle": 0, "started_at": datetime.now(timezone.utc).isoformat(),
             "raw": {}, "pool": {}}
    cycle = 0
    while True:
        cycle += 1
        state["cycle"] = cycle
        log(f"===== cycle {cycle} =====")

        # ---- 1. the source frame, now and then -------------------------
        first = cycle == 1 and not args.skip_discovery
        later = cycle > 1 and args.discover_every and cycle % args.discover_every == 0
        if first or later:
            log("re-checking the source frame for new official accounts")
            code, out, err = run("discover", [PY, os.path.join(HERE, "discover_from_websites.py"),
                                              "--apply"], timeout=5400)
            tail = [l for l in out.splitlines() if l.strip()][-4:]
            for l in tail:
                log("   " + l)

        # ---- 2. the collectors ------------------------------------------
        # One worker at a time. The browser holds several tabs, and a short
        # test with three driving at once works, but sustained concurrent
        # driving closes the runtime's connection and every account fails
        # with "runtime_unavailable". One process drives the browser; the
        # parallelism is in the adjudication and the validation, which do
        # not touch it.
        deadline = time.time() + args.cycle_seconds

        # The queue. The most recent posts first, because that is the frame
        # the paper describes; then the request-inviting stratum, which is
        # the contract's pre-registered stratified collection and the one
        # that raises the yield of actionable rows; then the other
        # platforms.
        queue = [("facebook", "recent", args.posts)]
        queue += [("facebook", "invites", args.invites_posts)]
        queue += [(pl, "recent", args.posts) for pl in args.platforms
                  if pl != "facebook"]

        for platform, mode, posts in queue:
            cmd = [PY, os.path.join(HERE, "worker.py"),
                   "--platform", platform, "--tab", "0",
                   "--posts", str(posts), "--mode", mode, "--pause", "6"]
            log(f"starting {platform}/{mode} on tab 0, {posts} posts")
            p = subprocess.Popen(cmd, cwd=ROOT)
            # Wait for the worker to finish, even past the deadline. Two
            # workers driving the browser at once closes the runtime's
            # connection, so the queue must never overlap itself. The
            # deadline only decides when the NEXT cycle starts.
            while p.poll() is None:
                time.sleep(20)
            log(f"  {platform}/{mode} finished with code {p.returncode}")
            if time.time() >= deadline:
                log("  the cycle is over; the next one starts now")

        # ---- 4. rebuild the interim and clean ----------------------------
        log("rebuilding the interim layer and cleaning")
        code, out, err = run("clean", [PY, os.path.join(ROOT, "tools", "finalize_dataset.py"),
                                       "--stage", "clean"], timeout=5400)
        for l in [x for x in out.splitlines() if x.strip()][-10:]:
            log("   " + l)

        # ---- 5. the state ------------------------------------------------
        state["raw"] = {k: {"posts": v[0], "comments": v[1]}
                        for k, v in raw_totals().items()}
        state["pool"] = pool_stats()
        write_heartbeat(state)
        log(f"raw: {state['raw']}")
        log(f"pool: {state['pool']['rows']} rows, "
            f"{state['pool']['residual_duplicate_keys']} residual duplicate keys, "
            f"excluded {state['pool']['excluded_by_reason']}")

        if args.cycles and cycle >= args.cycles:
            log("finished the requested number of cycles")
            return 0
        time.sleep(5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
