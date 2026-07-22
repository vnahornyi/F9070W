#!/usr/bin/env python3
"""Build a theme: PNG overrides -> .data screens -> patched ROOTFS partition.

A theme is a directory of PNGs named after the sprite index they replace:

    themes/vw/Main/00.png        replaces sprite 0 of Main.data
    themes/vw/Main/09.png        replaces sprite 9 of Main.data
    themes/vw/SystemBar/03.png   ...

Every PNG must match the stock sprite's exact width and height. Anything you do
not supply keeps its stock bytes, so a half-finished theme still boots.

    python3 tools/build.py vw                # screens only -> out/
    python3 tools/build.py vw --image        # also patch data_udisk.fex
"""
import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from formats import datav1, minfs  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), '..')
DATA = os.path.join(ROOT, 'stock/rootfs/apps/Data')
PARTS = os.path.join(ROOT, 'stock/partitions')
OUT = os.path.join(ROOT, 'out')


def png_to_raw(path: str, sp: datav1.Sprite) -> bytes:
    from PIL import Image
    im = Image.open(path)
    if im.size != (sp.width, sp.height):
        raise ValueError(
            f'{path}: is {im.width}x{im.height}, stock sprite is {sp.width}x{sp.height}')
    if sp.depth == 4:
        px = im.convert('RGBA').tobytes('raw', 'BGRA')
    elif sp.depth == 3:
        px = im.convert('RGB').tobytes('raw', 'BGR')
    elif sp.depth == 2:
        px = im.convert('RGB').tobytes('raw', 'BGR;16')
    else:
        raise ValueError(f'{path}: unsupported stock depth {sp.depth}')
    return sp.pack(px)


def build_screens(theme: str) -> dict[str, bytes]:
    tdir = os.path.join(ROOT, 'themes', theme)
    if not os.path.isdir(tdir):
        raise SystemExit(f'no such theme: {tdir}')
    built, changed = {}, 0
    for screen in sorted(os.listdir(tdir)):
        sdir = os.path.join(tdir, screen)
        if not os.path.isdir(sdir):
            continue
        stock = os.path.join(DATA, f'{screen}.data')
        if not os.path.exists(stock):
            raise SystemExit(f'{screen}: no stock screen named {screen}.data')
        d = open(stock, 'rb').read()
        sprites = {s.idx: s for s in datav1.sprites(d)}
        replace = {}
        for png in sorted(os.listdir(sdir)):
            if not png.lower().endswith('.png'):
                continue
            idx = int(os.path.splitext(png)[0])
            if idx not in sprites:
                raise SystemExit(f'{screen}: sprite {idx} does not exist '
                                 f'(stock has {len(sprites)})')
            replace[idx] = png_to_raw(os.path.join(sdir, png), sprites[idx])
        if not replace:
            continue
        built[f'{screen}.data'] = datav1.rebuild(d, replace)
        changed += len(replace)
        print(f'  {screen:24} {len(replace)}/{len(sprites)} sprites')
    if not built:
        raise SystemExit('theme is empty - nothing to build')
    print(f'  {len(built)} screens, {changed} sprites replaced')
    return built


def write_screens(built: dict[str, bytes]):
    dst = os.path.join(OUT, 'apps/Data')
    shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(dst, exist_ok=True)
    for name, blob in built.items():
        open(os.path.join(dst, name), 'wb').write(blob)
    print(f'screens -> {dst}')


def patch_image(built: dict[str, bytes]):
    part = next((os.path.join(PARTS, f) for f in os.listdir(PARTS)
                 if open(os.path.join(PARTS, f), 'rb').read(5) == minfs.MAGIC), None)
    if not part:
        raise SystemExit('no MINFS partition in stock/partitions')
    d = open(part, 'rb').read()
    before = minfs.free_offset(d)
    for name, blob in built.items():
        d = minfs.replace(d, f'/apps/Data/{name}', blob)
    after = minfs.free_offset(d)
    dst = os.path.join(OUT, os.path.basename(part))
    os.makedirs(OUT, exist_ok=True)
    open(dst, 'wb').write(d)
    print(f'image   -> {dst}')
    print(f'  free tail {len(d) - before} -> {len(d) - after} bytes')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('theme')
    ap.add_argument('--image', action='store_true',
                    help='also patch the ROOTFS partition')
    args = ap.parse_args()

    print(f'building theme "{args.theme}"')
    built = build_screens(args.theme)
    write_screens(built)
    if args.image:
        patch_image(built)


if __name__ == '__main__':
    main()
