---
name: unpack-firmware
description: Unpack an F9070W firmware image into the stock/ tree — partitions, MINFS rootfs and sprite PNGs. Use when stock/ is missing or stale, when a fresh clone needs the firmware, when the vendor .rar / LTTF133.img has to be opened, or when a stock-marked test skips because stock/ is not there.
---

# Unpack the firmware

All commands run from the repository root. Read `AGENTS.md` first if you have not.

## What you need

The vendor archive `F9070W.rar`, or the `LTTF133.img` inside it. Nothing in this
repository can regenerate that file — everything else under `stock/` can be
regenerated from it.

`stock/` is **gitignored** (~57 MB) and regenerable. `out/` is gitignored too.
Never write into `stock/` by hand.

## Do it

```bash
./.venv/bin/python tools/unpack.py ~/Downloads/F9070W.rar --png
```

Already have the raw image instead of the archive:

```bash
./.venv/bin/python tools/unpack.py stock/LTTF133.img --png
```

Real output:

```
image -> /Users/…/F9070W/tools/../stock/LTTF133.img
partitions -> /Users/…/F9070W/tools/../stock/partitions
rootfs -> /Users/…/F9070W/tools/../stock/rootfs  (188 stored as-is, 69 melis-lzma [approximate])
sprites -> /Users/…/F9070W/tools/../stock/png  (1128 PNG)
```

Takes about 3 seconds in total.

## Flags

| form | effect |
|---|---|
| `unpack.py <path.rar>` | extracts the `.img` out of the archive (needs `bsdtar`), then unpacks it |
| `unpack.py <path.img>` | copies the image to `stock/` and unpacks it |
| `unpack.py` (no argument) | reuses whatever is already in `stock/`; does nothing if `stock/rootfs/` exists |
| `--png` | additionally exports every sprite to `stock/png/<Screen>/NN.png` |

`--png` is what you want in almost every case: it is the input side of
`.claude/skills/build-theme/`. It deletes and rewrites `stock/png/` each run.

## What lands where

```
stock/LTTF133.img      the pristine vendor image — irreplaceable, read-only
stock/partitions/      the 25 IMAGEWTY items, raw
stock/rootfs/          the MINFS tree out of data_udisk.fex (257 files)
stock/rootfs/apps/Data/*.data   the 75 DATAV1.0 UI screens
stock/png/<Screen>/NN.png       1128 sprites, one PNG per sprite
```

## Check it worked

```bash
./.venv/bin/python tools/mkfixtures.py
```

```
8/8 fixtures match stock/
```

That compares the committed golden files in `tests/fixtures/` against what the
tree you just unpacked produces, so it catches a truncated or wrong image. If it
says `STALE`, **do not** run `--update` — see rule 11 in `AGENTS.md`.

Then the stock-marked suite becomes runnable:

```bash
./.venv/bin/python -m pytest -q -m stock
```

## Things that will bite you

* **The 69 melis-lzma files in `stock/rootfs/` are approximate.** `.mod`, `.drv`,
  `.plg` and `.axf` are decompressed by a heuristic that overshoots `init.axf` by
  30 bytes and gets three files wrong. Read them, do not trust them byte for
  byte, and never write one back. See `docs/formats/melis-lzma.md`.
* **The 75 `.data` screens and everything else are stored uncompressed**, so they
  *are* exact. Theming only touches those.
* **Duplicate item names.** `boot_pkg_uboot_nor.fex` occurs twice; the unpacker
  writes the second one as `boot_pkg_uboot_nor.fex.1`. They are two different
  partitions with different subtypes — see `docs/formats/imagewty.md`.
* A depth the exporter cannot write prints `skip <Screen>/<idx>: depth N`. All
  1128 stock sprites are depth 4/3/2 and all export, so any `skip` line is a
  finding, not noise.
