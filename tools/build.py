#!/usr/bin/env python3
"""Build a theme: PNG overrides -> .data screens -> ROOTFS partition -> .img.

A theme is a directory of PNGs named after the sprite index they replace:

    themes/vw/Main/00.png        replaces sprite 0 of Main.data
    themes/vw/Main/09.png        replaces sprite 9 of Main.data
    themes/vw/SystemBar/03.png   ...

Every PNG must match the stock sprite's exact width and height. Anything you do
not supply keeps its stock bytes, so a half-finished theme still boots. An empty
theme is legal with --image/--img and reproduces the stock partition and image
byte for byte - that is the regression test the whole toolchain rests on.

    python3 tools/build.py vw                # screens only -> out/
    python3 tools/build.py vw --image        # also patch data_udisk.fex
    python3 tools/build.py vw --img          # also assemble out/LTTF133.img
"""
import argparse
import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from formats import datav1, imagewty, minfs  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), '..')
STOCK = os.path.join(ROOT, 'stock')
DATA = os.path.join(ROOT, 'stock/rootfs/apps/Data')
PARTS = os.path.join(ROOT, 'stock/partitions')
OUT = os.path.join(ROOT, 'out')

# RGB565 quantisation tables. Pillow ships a BGR;16 decoder but no encoder, so
# the packing below is written out by hand; these two tables are the exact
# inverse of what that decoder produces, verified over all 65536 code points
# and over every depth-2 sprite in the stock firmware (tests/test_build.py).
_R5 = bytes((c * 31 + 127) // 255 for c in range(256))
_G6 = bytes((c * 63 + 127) // 255 for c in range(256))


def rgb_to_565(rgb: bytes) -> bytes:
    """Pack tightly-packed RGB888 into little-endian RGB565 (Pillow BGR;16)."""
    r = rgb[0::3].translate(_R5)
    g = rgb[1::3].translate(_G6)
    b = rgb[2::3].translate(_R5)
    out = bytearray(2 * len(r))
    out[0::2] = bytes(((gv & 7) << 5) | bv for gv, bv in zip(g, b))
    out[1::2] = bytes((rv << 3) | (gv >> 3) for rv, gv in zip(r, g))
    return bytes(out)


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
        px = rgb_to_565(im.convert('RGB').tobytes('raw', 'RGB'))
    else:
        raise ValueError(f'{path}: unsupported stock depth {sp.depth}')
    return sp.pack(px)


def theme_dir(theme: str) -> str:
    """A theme is either a path or a name under themes/."""
    if os.path.isdir(theme):
        return theme
    return os.path.join(ROOT, 'themes', theme)


def stock_image() -> str:
    """The pristine .img parked in stock/ by tools/unpack.py."""
    for n in sorted(os.listdir(STOCK) if os.path.isdir(STOCK) else []):
        if n.lower().endswith('.img'):
            return os.path.join(STOCK, n)
    raise SystemExit('no pristine .img in stock/ - run tools/unpack.py first')


def build_screens(theme: str) -> dict[str, bytes]:
    tdir = theme_dir(theme)
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
    print(f'  {len(built)} screens, {changed} sprites replaced')
    return built


def write_screens(built: dict[str, bytes], out: str = OUT):
    dst = os.path.join(out, 'apps/Data')
    shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(dst, exist_ok=True)
    for name, blob in built.items():
        open(os.path.join(dst, name), 'wb').write(blob)
    print(f'screens -> {dst}')


def patch_partition(built: dict[str, bytes]) -> tuple[str, bytes]:
    """Patch every built screen into the stock MINFS partition."""
    part = next((os.path.join(PARTS, f) for f in sorted(os.listdir(PARTS))
                 if open(os.path.join(PARTS, f), 'rb').read(5) == minfs.MAGIC), None)
    if not part:
        raise SystemExit('no MINFS partition in stock/partitions')
    d = open(part, 'rb').read()
    before = minfs.free_offset(d)
    for name, blob in built.items():
        d = minfs.replace(d, f'/apps/Data/{name}', blob)
    after = minfs.free_offset(d)
    print(f'  free tail {len(d) - before} -> {len(d) - after} bytes')
    return os.path.basename(part), d


def write_partition(name: str, data: bytes, out: str = OUT) -> str:
    os.makedirs(out, exist_ok=True)
    dst = os.path.join(out, name)
    open(dst, 'wb').write(data)
    print(f'image   -> {dst}')
    return dst


def write_img(name: str, data: bytes, out: str = OUT) -> str:
    """Assemble the full IMAGEWTY image around the patched partition."""
    src = stock_image()
    img = open(src, 'rb').read()
    new = imagewty.build(img, {name: data})
    os.makedirs(out, exist_ok=True)
    dst = os.path.join(out, os.path.basename(src))
    open(dst, 'wb').write(new)
    print(f'img     -> {dst}')
    print(f'  image size {len(new)} bytes')
    for was, now in zip(imagewty.parse(img), imagewty.parse(new)):
        if was.name == name:
            continue
        a, b = imagewty.extract(img, was), imagewty.extract(new, now)
        if a != b:
            print(f'  V-sum {now.name:20} {a[:4].hex()} -> {b[:4].hex()}')
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('theme')
    ap.add_argument('--image', action='store_true',
                    help='also patch the ROOTFS partition')
    ap.add_argument('--img', action='store_true',
                    help='also assemble the full LTTF133.img')
    ap.add_argument('--out', default=OUT, help='output directory')
    args = ap.parse_args()

    print(f'building theme "{args.theme}"')
    built = build_screens(args.theme)
    if not built and not (args.image or args.img):
        raise SystemExit('theme is empty - nothing to build')
    write_screens(built, args.out)
    if args.image or args.img:
        name, part = patch_partition(built)
        write_partition(name, part, args.out)
        if args.img:
            write_img(name, part, args.out)


if __name__ == '__main__':
    main()
