#!/usr/bin/env python3
"""Regression guard: unpack every screen and rebuild it with no changes.

If rebuild-without-changes is not byte-identical to the original, the writer is
lying about something and no theme built with it can be trusted. Run this before
and after touching anything in formats/.

    python3 tools/verify.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from formats import datav1, minfs  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), '..')
DATA = os.path.join(ROOT, 'stock/rootfs/apps/Data')
PARTS = os.path.join(ROOT, 'stock/partitions')


def check_screens() -> bool:
    if not os.path.isdir(DATA):
        raise SystemExit('run tools/unpack.py first')
    ok = bad = sprites = pixels = 0
    for name in sorted(os.listdir(DATA)):
        d = open(os.path.join(DATA, name), 'rb').read()
        try:
            same = datav1.rebuild(d) == d
            sp = datav1.sprites(d)
            sprites += len(sp)
            pixels += sum(s.width * s.height for s in sp)
        except Exception as e:
            print(f'  ERR  {name}: {e}')
            bad += 1
            continue
        if same:
            ok += 1
        else:
            print(f'  DIFF {name}')
            bad += 1
    print(f'  screens byte-identical : {ok}/{ok + bad}')
    print(f'  sprites                : {sprites}  ({pixels / 1e6:.1f} Mpx)')
    return bad == 0


def check_rootfs():
    part = next((os.path.join(PARTS, f) for f in os.listdir(PARTS)
                 if open(os.path.join(PARTS, f), 'rb').read(5) == minfs.MAGIC), None)
    if not part:
        return
    d = open(part, 'rb').read()
    files = minfs.files(d)
    free = len(d) - minfs.free_offset(d)
    print(f'  MINFS files            : {len(files)} '
          f'({sum(1 for f in files if not f.compressed)} stored uncompressed)')
    print(f'  free tail              : {free} bytes ({free / 1024 / 1024:.2f} MB)')


if __name__ == '__main__':
    print('DATAV1.0 round-trip')
    good = check_screens()
    check_rootfs()
    print('\nOK' if good else '\nFAILED')
    sys.exit(0 if good else 1)
