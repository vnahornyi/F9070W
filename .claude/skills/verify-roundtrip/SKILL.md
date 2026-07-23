---
name: verify-roundtrip
description: The mandatory check before committing anything under formats/ — proves that a change-nothing rebuild is still byte-identical at every layer. Use before any commit that touches formats/imagewty.py, minfs.py, datav1.py or melislzma.py, before touching tools/build.py or tools/unpack.py, whenever a round-trip or golden fixture fails, and whenever asked whether a change is safe.
---

# Verify the round trip

**This is not optional.** `AGENTS.md` rule 3: any change in `formats/` ships with
a round-trip test in the same commit, and this procedure is how you know the test
is telling the truth.

The whole toolchain rests on one property: *no changes must mean no changed
bytes*, at every layer — IMAGEWTY → MINFS → DATAV1.0 → zlib → pixels. If that
holds, a difference in the output can only exist where something was changed
deliberately. If it breaks anywhere, every image this repository produces is
suspect.

The layers nest, so a bug in a lower one is invisible until the top layer is
rebuilt. That is why the fast suite alone is not enough.

## Run it in this order

### 1. Fast suite — no `stock/` needed

```bash
./.venv/bin/python -m pytest -q -m "not stock"
```

```
......................................sss.........sss................... [ 96%]
...                                                                      [100%]
69 passed, 6 skipped, 62 deselected in 0.17s
```

Under a second. Run it constantly while you work. It runs off the golden files in
`tests/fixtures/`, which is also what a clone without `stock/` gets.

### 2. Golden fixtures still match the real firmware

```bash
./.venv/bin/python tools/mkfixtures.py
```

```
8/8 fixtures match stock/
```

`STALE` here means the committed expectation and the real firmware disagree.
**Do not run `--update` to make it go away** (rule 11). Work out which side moved
and write it up in `docs/findings.md` in the same commit.

### 3. Full stock suite — the one that actually catches things

```bash
./.venv/bin/python tools/verify.py
```

or equivalently:

```bash
./.venv/bin/python -m pytest -q -m stock
```

```
..............................................................           [100%]
62 passed, 75 deselected in 187.98s (0:03:07)
```

This runs against the real 57 MB tree: all 25 partitions, all 257 MINFS files,
all 75 screens, all 1128 sprites. It takes **about three minutes**, mostly
because `minfs.files()` costs ~1.4 s per call (finding 6 in `docs/findings.md`).
Let it finish; do not cut it short with `-x` and call the change verified.

Extra flags pass straight through, and `--all` runs the whole suite:

```bash
./.venv/bin/python tools/verify.py -q --all
```

### 4. The end-to-end control: an empty theme reproduces the vendor image

The single most informative command in the repository. It drives every layer in
both directions and compares against the pristine file.

```bash
mkdir -p /tmp/empty-theme
./.venv/bin/python tools/build.py /tmp/empty-theme --img
cmp out/LTTF133.img stock/LTTF133.img && echo BYTE-IDENTICAL
```

```
building theme "/tmp/empty-theme"
  0 screens, 0 sprites replaced
screens -> /Users/…/F9070W/tools/../out/apps/Data
  free tail 2663808 -> 2663808 bytes
image   -> /Users/…/F9070W/tools/../out/data_udisk.fex
img     -> /Users/…/F9070W/tools/../out/LTTF133.img
  image size 18252800 bytes
BYTE-IDENTICAL
```

About 3 seconds. `free tail` unchanged at 2 663 808, image size exactly
18 252 800, no V-sum lines, and `cmp` silent. Anything else and you stop.

### 5. Nothing large or generated is staged

```bash
git status --short
```

`stock/`, `out/`, `*.img`, `*.fex` and `.claude/plans/` must not appear.
`.claude/skills/` and `tests/fixtures/` **are** committed on purpose.

## What each step would have caught

Not hypothetical — these are the actual regressions in this repository:

| failure | which step catches it |
|---|---|
| `datav1.Sprite.pack()` zeroing row padding (543/1128 sprites, 48 of 69 screens corrupted) | 3 and 4 — the fast suite passed |
| `imagewty.build()` keyed by name, rewriting the wrong `boot_pkg_uboot_nor.fex` | 3 |
| IMAGEWTY padding treated as one `0xCD` region instead of zeroes-then-`0xCD` | 4 — the image simply is not identical |
| a golden fixture drifting away from the firmware | 2 |

## If a step fails

1. **Do not commit.** Not even "the rest is green".
2. Do not weaken an assertion, relax a test, or regenerate a fixture to restore
   the green. That converts a caught bug into a shipped one.
3. Find the lowest failing layer first — IMAGEWTY, then MINFS, then DATAV1.0. An
   upper-layer failure is usually a lower-layer symptom.
4. Reduce it to the smallest failing thing: one fixture, one sprite, one
   partition. `tests/fixtures/black.data` (592 B, 0 sprites) and
   `wallpaper.data` are the smallest specimens in the repository.
5. Write the measurement down in `docs/findings.md` before changing code — with
   the numbers a program printed, not a recollection (rules 1 and 2).

## Before you commit a `formats/` change

* the new test is in **this** commit, not the next one
* it asserts a byte comparison, not "parses without raising"
* it covers the case that used to be wrong, by number (543 sprites, 69 screens,
  two `BOOTPKG-*` subtypes — cite the real count)
* unknown bytes are still carried verbatim, not zeroed or normalised (rule 4)
* anything you could not prove is marked `⚠️ UNVERIFIED` with the experiment that
  would settle it
