#!/usr/bin/env python3
"""Replace an arbitrary file inside the MINFS rootfs -> ROOTFS partition -> .img.

Where tools/build.py knows about sprites and screens, this knows about nothing:
it takes a path that already exists in the rootfs and a local file, and stores
that file's bytes verbatim in its place.

    python3 tools/patchfile.py /apps/Config.ini themes/config/Config.ini
    python3 tools/patchfile.py /apps/Config.ini out/Config.ini --img
    python3 tools/patchfile.py /a.txt a.txt /b.txt b.txt --img --out out

The path must already exist: a typo would otherwise become a new file nobody
reads, and the run would look successful. There is no create mode.

minfs.replace() stores the blob uncompressed, in place when it fits the stock
slot and in the free tail otherwise, so a replacement that is not larger than
the original never moves another file. Feeding a file back unchanged reproduces
the stock partition and the stock image byte for byte - that is the regression
test this tool rests on (tests/test_patchfile.py).

Without --img only the patched partition is written, which is enough for the
update/ delivery route; with --img the whole IMAGEWTY image is reassembled and
every V-sum that moved is printed.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from formats import minfs  # noqa: E402
from tools import build  # noqa: E402


def rootfs_partition() -> tuple[str, bytes]:
    """The stock MINFS partition, found by magic rather than by name."""
    parts = build.PARTS
    part = next((os.path.join(parts, f) for f in sorted(os.listdir(parts))
                 if open(os.path.join(parts, f), 'rb').read(5) == minfs.MAGIC), None)
    if not part:
        raise SystemExit('no MINFS partition in stock/partitions')
    return os.path.basename(part), open(part, 'rb').read()


def patch_files(pairs: dict[str, bytes]) -> tuple[str, bytes]:
    """Patch every path -> blob pair into the stock MINFS partition."""
    name, d = rootfs_partition()
    missing = [p for p in pairs if not _exists(d, p)]
    if missing:
        raise SystemExit('not in the rootfs: %s - patchfile.py never creates '
                         'a new file' % ', '.join(sorted(missing)))
    before = minfs.free_offset(d)
    for path, blob in pairs.items():
        was = minfs.find(d, path)
        d = minfs.replace(d, path, blob)
        now = minfs.find(d, path)
        where = ('in place' if now.offset == was.offset
                 else f'relocated {was.offset:#x} -> {now.offset:#x}')
        print(f'  {path:24} {was.stored} -> {now.stored} bytes, {where}')
    after = minfs.free_offset(d)
    print(f'  free tail {len(d) - before} -> {len(d) - after} bytes')
    return name, d


def _exists(d: bytes, path: str) -> bool:
    try:
        minfs.find(d, path)
    except KeyError:
        return False
    return True


def read_pairs(args: list[str]) -> dict[str, bytes]:
    if len(args) % 2:
        raise SystemExit('arguments come in pairs: <path-in-rootfs> <local-file>')
    pairs = {}
    for path, local in zip(args[0::2], args[1::2]):
        if not path.startswith('/'):
            raise SystemExit(f'{path}: a rootfs path is absolute, e.g. /apps/Config.ini')
        if not os.path.isfile(local):
            raise SystemExit(f'no such file: {local}')
        pairs[path] = open(local, 'rb').read()
    return pairs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('pairs', nargs='+', metavar='PATH FILE',
                    help='rootfs path and the local file to store there')
    ap.add_argument('--img', action='store_true',
                    help='also assemble the full LTTF133.img')
    ap.add_argument('--out', default=os.path.normpath(build.OUT),
                    help='output directory')
    args = ap.parse_args()

    pairs = read_pairs(args.pairs)
    print(f'patching {len(pairs)} file(s) into the rootfs')
    name, part = patch_files(pairs)
    build.write_partition(name, part, args.out)
    if args.img:
        build.write_img(name, part, args.out)


if __name__ == '__main__':
    main()
