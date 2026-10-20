"""
run_all.py — run every test in this folder.

    python tests/run_all.py

Each test module exposes `run()` returning a list of failure strings.
Exits non-zero if anything fails.
"""

from __future__ import annotations

import importlib
import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "src"))

MODULES = ["test_clean", "test_to_interim", "test_scraper", "test_split_validate"]


def main() -> int:
    total_failures = []
    for name in MODULES:
        path = os.path.join(HERE, f"{name}.py")
        if not os.path.exists(path):
            print(f"  SKIP  {name} (not present)")
            continue
        print(f"\n{'=' * 66}\n{name}\n{'=' * 66}")
        try:
            mod = importlib.import_module(name)
            failures = mod.run()
        except Exception:
            traceback.print_exc()
            failures = [f"{name} raised an exception"]
        if failures:
            total_failures.extend(failures)
            print(f"\n  {len(failures)} failure(s) in {name}")
        else:
            print(f"\n  {name}: OK")

    print(f"\n{'=' * 66}")
    if total_failures:
        print(f"{len(total_failures)} TOTAL FAILURES")
        for f in total_failures:
            print(f"  - {f}")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
