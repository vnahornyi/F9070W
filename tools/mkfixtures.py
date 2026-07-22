#!/usr/bin/env python3
"""Extract golden files from stock/ into tests/fixtures/.

    python3 tools/mkfixtures.py            # check the committed fixtures
    python3 tools/mkfixtures.py --update   # regenerate them

Six small DATAV1.0 screens are copied verbatim out of stock/rootfs/apps/Data/,
lowercased, plus two snapshots derived from them:

    sprites.json  w/h/depth/stride/raw_len/header of every sprite of every screen
    png.sha256    SHA-256 of each sprite exported through tools/unpack.py

They exist so a clone without the ~40 MB stock/ tree still runs the test suite.
Never regenerate silently: a changed snapshot is either a real regression or a
finding that belongs in docs/findings.md.

Coverage, measured on the stock tree (`header` in sprites.json pins it down):

    header 24 B  788 stock sprites in 55 screens  -> setuplogo
    header 32 B  340 stock sprites in 14 screens  -> volumebar, setupversion
                 (its +0x18..0x20 is always 01 00 00 00 00 00 00 00)
    depth 2, 3   covered
    depth 4      NOT covered - every screen holding a depth-4 sprite
                 (RadioRds 93 KB, MainApp 452 KB, Main 575 KB) blows the
                 100 KB fixture budget. Depth-4 assertions therefore belong in
                 a @pytest.mark.stock test. Do not synthesise a fixture for it.
"""
import argparse
import hashlib
import io
import json
import os
import sys
from dataclasses import dataclass

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from formats import datav1  # noqa: E402
from tools import unpack  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), '..')
DATA = os.path.join(ROOT, 'stock', 'rootfs', 'apps', 'Data')
FIXTURES = os.path.join(ROOT, 'tests', 'fixtures')


@dataclass
class Golden:
    """One expected fixture: file name, byte size and sprite count."""
    name: str
    size: int
    sprites: int


GOLDEN = [
    Golden('black.data', 592, 0),
    Golden('wallpaper.data', 592, 0),
    Golden('tipbox.data', 1068, 0),
    Golden('volumebar.data', 8522, 13),
    Golden('setupversion.data', 8118, 2),
    Golden('setuplogo.data', 8128, 5),
]


def source_of(name: str) -> str:
    """stock/rootfs/apps/Data/ stores the screens CamelCased; match loosely."""
    for n in sorted(os.listdir(DATA)):
        if n.lower() == name:
            return os.path.join(DATA, n)
    raise SystemExit(f'{name}: not found in {DATA}')


def png_sha256(sp: datav1.Sprite) -> str:
    buf = io.BytesIO()
    im = unpack.sprite_image(sp)
    if im is None:
        raise SystemExit(f'sprite {sp.idx}: depth {sp.depth} is not exportable')
    im.save(buf, format='PNG')
    return hashlib.sha256(buf.getvalue()).hexdigest()


def generate() -> dict[str, bytes]:
    """Build every fixture file in memory, keyed by its name in tests/fixtures/."""
    out: dict[str, bytes] = {}
    snapshot: dict[str, list[dict]] = {}
    digests: list[str] = []
    for g in GOLDEN:
        blob = open(source_of(g.name), 'rb').read()
        if len(blob) != g.size:
            print(f'!! {g.name}: {len(blob)} bytes, plan says {g.size}')
        items = datav1.sprites(blob)
        if len(items) != g.sprites:
            print(f'!! {g.name}: {len(items)} sprites, plan says {g.sprites}')
        out[g.name] = blob
        snapshot[g.name] = [
            {'idx': sp.idx, 'width': sp.width, 'height': sp.height,
             'depth': sp.depth, 'stride': sp.stride, 'raw_len': sp.raw_len,
             'header': len(sp.header)}
            for sp in items
        ]
        for sp in items:
            digests.append(f'{png_sha256(sp)}  {g.name}/{sp.idx:02}.png')

    out['sprites.json'] = (json.dumps(snapshot, indent=2) + '\n').encode()
    out['png.sha256'] = ('\n'.join(digests) + '\n').encode()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--update', action='store_true',
                    help='rewrite tests/fixtures/ from stock/')
    args = ap.parse_args()

    if not os.path.isdir(DATA):
        raise SystemExit(f'no {DATA} - run tools/unpack.py first')

    want = generate()
    if args.update:
        os.makedirs(FIXTURES, exist_ok=True)
        for name, blob in want.items():
            open(os.path.join(FIXTURES, name), 'wb').write(blob)
        total = sum(len(b) for b in want.values())
        print(f'fixtures -> {FIXTURES}  ({len(want)} files, {total} bytes)')
        return

    bad = 0
    for name, blob in want.items():
        path = os.path.join(FIXTURES, name)
        have = open(path, 'rb').read() if os.path.exists(path) else None
        if have != blob:
            print(f'STALE {name}')
            bad += 1
    print(f'{len(want) - bad}/{len(want)} fixtures match stock/')
    if bad:
        raise SystemExit('run with --update, and explain the change in docs/findings.md')


if __name__ == '__main__':
    main()
