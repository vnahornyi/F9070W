---
name: reverse-format
description: How to decode an undocumented binary format in this repository without guessing — smallest specimen first, diff pair, byte-identical round trip before any field is named. Use when starting on the DATAV1.0 layout section, font22.sft, the sunxi-package container, melis-lzma, the MINFS chunk table, or any unknown blob or field, and when a claim about an offset or a field's meaning has to be established.
---

# Reverse a new format

Every correct result in this repository came out of this order. Every wrong one
came from skipping a step — usually step 4, interpreting a field before the round
trip proved the parse.

Read `AGENTS.md` and `docs/findings.md` first. `docs/findings.md` is the record of
what a confident guess costs here.

## The order — do not reorder it

### 1. Start from the smallest specimen

The smallest file that contains the structure. Small enough that you can read the
whole hex dump, and every byte you cannot explain is visible rather than lost in
megabytes.

Already picked out for you:

| target | smallest specimen |
|---|---|
| DATAV1.0 layout section | `tests/fixtures/black.data`, `wallpaper.data` — 592 B, **zero sprites**, pure layout; then `tipbox.data` (1068 B) |
| DATAV1.0 sprites | `tests/fixtures/volumebar.data` (8522 B, 13 sprites), `setupversion.data` (8118 B, 32-byte headers) |
| IMAGEWTY items | `arisc.fex` — 15 bytes |
| MINFS entries | any `/apps/Language/*.txt`, plain UTF-16LE text |

```bash
xxd tests/fixtures/black.data | head -6
```

```
00000000: 4400 4100 5400 4100 5600 3100 2e00 3000  D.A.T.A.V.1...0.
00000010: 2000 0000 4c02 0000 0000 0000 0000 0000   ...L...........
00000020: 2c02 0000 1400 0000 0000 0000 0000 0000  ,...............
00000030: 0004 0000 5802 0000 0100 0000 0500 0000  ....X...........
00000040: 5c00 0000 0600 0000 2802 0000 0600 0000  \.......(.......
00000050: 3402 0000 0600 0000 4002 0000 cc01 0000  4.......@.......
```

Do not start on `init.axf` (2.5 MB) or `melis_pkg_nor.fex` (1.6 MB).

### 2. Get a diff pair

One structure is a hex dump. Two that differ in one known way is a decoder.

Ways to get a pair here, in order of preference:

* **Two stock files that differ in one property.** `black.data` and
  `wallpaper.data` are both 592 bytes — identical size, different window name.
  Every differing byte is on the path from "name" to "bytes".
* **A file and its own rebuild** with one field deliberately changed through the
  existing code, if a writer already exists for that layer.
* **A second vendor image.** The strongest evidence available, and this repository
  does not have one. Several open questions — is `0xCD` a stable vendor padding?
  what does the 32-byte sprite header mean? — cannot be settled without it,
  precisely because the value is constant in this image. A constant carries no
  information.

```bash
cmp -l tests/fixtures/black.data tests/fixtures/wallpaper.data | head -5
cmp -l tests/fixtures/black.data tests/fixtures/wallpaper.data | wc -l
```

```
   101   0 126
   103   0 151
   105   0 145
   107   0 167
   109   0 123
      21
```

21 differing bytes out of 592, all from byte 101 onward — `cmp -l` counts from 1,
so that is offset `0x64`, the UTF-16LE window name, every second byte because the
high halves are zero. Count the differing bytes and see where they cluster before
you name anything.

### 3. Prove a byte-identical round trip **before** interpreting any field

This is the step that separates this repository from a wiki page of guesses.

Write `parse()` and `rebuild()` and assert:

```python
assert rebuild(parse(data)) == data
```

over **every** stock specimen, not one. Only when that holds do you know your
structure boundaries are right. A parse that "looks right" and a parse that
round-trips are different things: field boundaries can be off and every value
still look plausible.

While doing this, carry every byte you have not explained **verbatim** — do not
zero it, do not normalise it, do not "clean it up". `datav1.Sprite.pack()`
synthesised row padding as zeroes because padding is obviously padding; 543 of
the 1128 stock sprites store *non-zero* padding, and the change-nothing round trip
was silently corrupting 48 of the 69 themeable screens. See rule 4 in
`AGENTS.md`.

The round trip goes in `tests/` in the same commit (rule 3). Give it a name that
states the measurement, in the style already there:
`test_stock_header_sizes_split_55_and_14_screens`.

### 4. Only now name fields, one at a time

For each candidate field, measure across the whole corpus before you name it:

* the set of distinct values, with counts
* correlation with something already known — a length, a count, a file extension
* whether it round-trips when perturbed through the existing writer

```bash
./.venv/bin/python -c "
import sys, collections; sys.path.insert(0, '.')
from formats import datav1
import os
hist = collections.Counter()
d = 'stock/rootfs/apps/Data'
for n in sorted(os.listdir(d)):
    for s in datav1.sprites(open(os.path.join(d, n), 'rb').read()):
        hist[len(s.header)] += 1
print(dict(hist))
"
```

```
{24: 788, 32: 340}
```

That one histogram is what replaced the plan's "bytes `+0x18..0x20` are non-zero
in 14 screens" with the real finding: two header *sizes*, and the 32-byte
variant's tail is the constant `01 00 00 00 00 00 00 00`, which tells you nothing
at all about its meaning. Say so, and mark it `⚠️ UNVERIFIED`.

A correlation is the strongest thing you will usually get. `+0x10` of a MINFS
entry exceeds `0x100` in exactly **69** entries — and 69 is exactly the number of
compressed files. That correlation *is* the finding; without it the high bits
look like noise. (An earlier session reported "20 of 273 entries" and the finding
stayed invisible — rule 2: re-measure everything.)

### 5. Write it down before you build on it

Two places, both in the same commit as the code:

* `docs/formats/<name>.md` — the layout, the evidence, the test names that pin it
* `docs/findings.md` — what was measured, and where a plan or an earlier session
  said something different, quoted next to the measurement

Every claim carries the command or the test that proves it. Everything else gets
`⚠️ UNVERIFIED` plus the experiment that would settle it.

## Rules of evidence

* **A number you did not personally produce is a hypothesis.** Plans, subagents,
  earlier sessions and previous docs are all leads. Re-run the measurement.
* **A constant value proves nothing.** If a field is the same in all 1128 samples,
  you have learned that you cannot learn its meaning from this image.
* **Correlate before you name.** "69 entries" is noise; "69 entries, and 69 is the
  compressed-file count" is a decoder.
* **A name is not an address.** `boot_pkg_uboot_nor.fex` occurs twice with
  different subtypes. Index by position; refuse ambiguity loudly.
* **Failing loudly beats coping quietly.** `vsum()` raises on a length that is not
  a multiple of 4 rather than ignoring the tail, because silently dropping bytes
  from a checksum is how corruption passes verification.
* **Never test a hypothesis on hardware.** Rule 8: the recovery path is
  unverified, so there is no experiment worth running on the device. Everything
  above is done on bytes.

## Before you claim the format is decoded

* `rebuild(parse(x)) == x` for **every** stock specimen, in a committed test
* every named field backed by a printed measurement over the whole corpus
* every unnamed byte still carried verbatim
* `./.venv/bin/python -m pytest -q -m stock` green — see
  `.claude/skills/verify-roundtrip/`
* `docs/` updated, unverified claims marked

## Where the open ones are

`docs/roadmap.md` lists every undecoded thing with an entry point: the DATAV1.0
layout section, the MINFS chunk table (the strongest lead, item 1), the
`sunxi-package` container, `font22.sft`, the `Config.ini` checksum.
