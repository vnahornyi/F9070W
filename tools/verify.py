#!/usr/bin/env python3
"""Regression guard: run the test suite against the real stock/ tree.

The round-trip checks this script used to carry by hand now live in tests/, so
there is exactly one implementation of "no changes must mean no changed bytes".
This stays as the short command to type before and after touching formats/.

    python3 tools/verify.py              # pytest -m stock
    python3 tools/verify.py -x -q        # extra flags go straight to pytest
    python3 tools/verify.py --all        # the whole suite, stock or not

Exit code is pytest's own: 0 all passed, 1 failures, 5 nothing collected.
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main() -> int:
    argv = sys.argv[1:]
    if '--all' in argv:
        argv = [a for a in argv if a != '--all']
        select = []
    else:
        select = ['-m', 'stock']
    cmd = [sys.executable, '-m', 'pytest', *select, *argv]
    print(' '.join(cmd))
    return subprocess.run(cmd, cwd=ROOT).returncode


if __name__ == '__main__':
    sys.exit(main())
