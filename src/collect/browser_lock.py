"""
browser_lock.py — one process drives the browser, enforced.

The Orca browser is driven through a single runtime. Two processes navigating at
the same time does not fail cleanly: the runtime closes the connection, and every
navigation in BOTH runs then fails with

    orca goto: runtime_unavailable The Orca runtime closed the connection before
    responding. Restart Orca and try again.

which looks exactly like the accounts being empty or the pages being blocked.
They are not. A morning was lost to this: three discovery processes survived the
kill of their parent supervisors and kept driving the tab, and the collector that
was supposed to be running reported every account as empty.

So whoever drives takes this lock. A second driver refuses to start.

The lock is a pid file. A stale file (whose pid is no longer running) is taken
over, so a crash never wedges the collector.

`os.kill(pid, 0)` is the usual way to test whether a pid is alive, and it is
wrong on Windows: there, `os.kill` with a signal other than CTRL_C_EVENT calls
TerminateProcess, so the "probe" would kill the process it was asking about. The
kernel is asked directly instead.
"""

from __future__ import annotations

import io
import os

LOCK = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "provenance", "browser.lock")


def _pid_alive(pid: int) -> bool:
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


def holder() -> int:
    """The pid that currently holds the lock, or 0."""
    try:
        raw = io.open(LOCK, encoding="utf-8").read().strip()
        return int(raw or 0)
    except (OSError, ValueError):
        return 0


def take(what: str = "this process", log=print) -> bool:
    """Claim the browser, or return False with the reason logged."""
    pid = holder()
    if pid and pid != os.getpid() and _pid_alive(pid):
        log(f"  the browser is already being driven by pid {pid}")
        log(f"  {what} exits rather than closing the runtime's connection")
        return False
    if pid and pid != os.getpid():
        log(f"  taking over a stale browser lock from pid {pid}")
    os.makedirs(os.path.dirname(LOCK), exist_ok=True)
    with io.open(LOCK, "w", encoding="utf-8", newline="") as fh:
        fh.write(str(os.getpid()))
    return True


def release() -> None:
    if holder() == os.getpid():
        try:
            os.remove(LOCK)
        except OSError:
            pass
