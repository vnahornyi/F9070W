#!/usr/bin/env python3
"""Unpack an F9070W firmware image into stock/.

    python3 tools/unpack.py F9070W.rar
    python3 tools/unpack.py update/LTTF133.img
    python3 tools/unpack.py --png            # also export every sprite as PNG

Produces:
    stock/partitions/   the 25 IMAGEWTY partitions
    stock/rootfs/       the MINFS tree from data_udisk.fex
    stock/png/<Screen>/NN.png
"""
import argparse
import os
import shutil
import subprocess
import sys
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from formats import datav1, imagewty, minfs  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), '..')
STOCK = os.path.join(ROOT, 'stock')


def from_rar(path: str) -> str:
    dst = os.path.join(STOCK, '_rar')
    shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(dst, exist_ok=True)
    subprocess.run(['bsdtar', '-xf', path, '-C', dst], check=True)
    for base, _, names in os.walk(dst):
        for n in names:
            if n.lower().endswith('.img'):
                return os.path.join(base, n)
    raise SystemExit('no .img found inside the archive')


def unpack_partitions(img: str) -> str:
    data = open(img, 'rb').read()
    out = os.path.join(STOCK, 'partitions')
    os.makedirs(out, exist_ok=True)
    seen: dict[str, int] = {}
    rootfs = None
    for item in imagewty.parse(data):
        name = item.name
        if name in seen:
            seen[name] += 1
            name = f'{name}.{seen[name]}'
        else:
            seen[name] = 0
        blob = imagewty.extract(data, item)
        open(os.path.join(out, name), 'wb').write(blob)
        if blob[:5] == minfs.MAGIC:
            rootfs = os.path.join(out, name)
    print(f'partitions -> {out}')
    if not rootfs:
        raise SystemExit('no MINFS partition found')
    return rootfs


def unpack_rootfs(part: str):
    data = open(part, 'rb').read()
    out = os.path.join(STOCK, 'rootfs')
    shutil.rmtree(out, ignore_errors=True)
    raw = comp = 0
    for node in minfs.files(data):
        dst = os.path.join(out, node.path.lstrip('/'))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        blob = data[node.offset:node.offset + node.stored]
        if node.compressed:
            from formats import melislzma
            blob = melislzma.decompress(blob, node.size)
            comp += 1
        else:
            raw += 1
        open(dst, 'wb').write(blob)
    print(f'rootfs -> {out}  ({raw} stored as-is, {comp} melis-lzma [approximate])')
    return out


def export_png(rootfs: str):
    try:
        from PIL import Image
    except ImportError:
        raise SystemExit('pip install pillow')
    src = os.path.join(rootfs, 'apps/Data')
    out = os.path.join(STOCK, 'png')
    shutil.rmtree(out, ignore_errors=True)
    total = 0
    for name in sorted(os.listdir(src)):
        d = open(os.path.join(src, name), 'rb').read()
        screen = name.removesuffix('.data')
        for sp in datav1.sprites(d):
            px = sp.pixels()
            size = (sp.width, sp.height)
            if sp.depth == 4:
                im = Image.frombytes('RGBA', size, px, 'raw', 'BGRA')
            elif sp.depth == 3:
                im = Image.frombytes('RGB', size, px, 'raw', 'BGR')
            elif sp.depth == 2:
                im = Image.frombytes('RGB', size, px, 'raw', 'BGR;16')
            else:
                print(f'  skip {screen}/{sp.idx}: depth {sp.depth}')
                continue
            os.makedirs(os.path.join(out, screen), exist_ok=True)
            im.save(os.path.join(out, screen, f'{sp.idx:02}.png'))
            total += 1
    print(f'sprites -> {out}  ({total} PNG)')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('source', nargs='?', help='.rar or .img (default: reuse stock/)')
    ap.add_argument('--png', action='store_true', help='export sprites as PNG')
    args = ap.parse_args()

    rootfs_dir = os.path.join(STOCK, 'rootfs')
    if args.source:
        img = from_rar(args.source) if args.source.lower().endswith('.rar') else args.source
        part = unpack_partitions(img)
        rootfs_dir = unpack_rootfs(part)
    elif not os.path.isdir(rootfs_dir):
        raise SystemExit('nothing in stock/ yet - pass the .rar or .img')

    if args.png:
        export_png(rootfs_dir)


if __name__ == '__main__':
    main()
