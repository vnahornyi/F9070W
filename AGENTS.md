# AGENTS.md

Rules for any AI working in this repository. They are not style preferences.

This is black-box reverse engineering of car-stereo firmware (Allwinner F133/D1s,
RISC-V). There is no vendor documentation and no source. The cost of a confident
wrong guess is a **bricked device with no verified way back** — `docs/hardware.md`
records that the recovery path has never been executed, so a mistake here is not
a failing test, it is a dead unit.

Every rule below exists because the mistake it forbids was actually made in this
repository and caught by a test. The reason is attached to each rule; if you ever
feel like an exception is justified, re-read the reason first.

Read `docs/findings.md` before you write anything. Do not restate this file's
content back into docs, and do not restate docs here.

---

## 1. Never state an offset, size or field meaning without running code that proves it

Not "the header is 24 bytes" — `print` it over every stock file and paste the
count. Not "these bytes are unknown flags" — show the histogram.

Three claims in the original plan were confidently wrong: IMAGEWTY padding is two
regions (zeroes to `align(length,16)`, then `0xCD` to 1024), not one region of
`0xCD`; the sprite "non-zero `+0x18..0x20` bytes" are actually a **header size**
difference (24 vs 32) with a constant tail; `data_udisk.fex` is followed by a
4-byte V-partition, not a 16-byte one. Each was written down as a fact, and each
one would have produced a wrong image.

## 2. A number reported by a plan, a subagent or an earlier session is not evidence

Re-measure it yourself before you repeat it.

A subagent reported "20 of 273 MINFS entries carry high bits in the name-length
field". The real number is **69 of 273** — and 69 is exactly the count of
compressed files, which is the entire finding. The wrong number hid it. Another
session reported "11 of 36 screens before the fix, 36 of 36 after"; re-measuring
gave 21 of 69. Both numbers were sincere and both were useless.

If your source is prose rather than a program's output, it is a hypothesis.

## 3. Any change in `formats/` ships with a round-trip test in the same commit

Same commit, not the next one. The layers nest — IMAGEWTY holds MINFS holds
DATAV1.0 holds zlib — and a bug in a lower layer only becomes visible at the top.
A commit that changes a parser and defers its test is a commit nobody can bisect
against.

Before committing anything under `formats/`, follow
`.claude/skills/verify-roundtrip/SKILL.md`. It is not optional.

## 4. Unknown bytes are carried verbatim — zeroing or "normalising" them is forbidden

This is the single most expensive rule to break, and it has been broken here
three times in three different places.

`datav1.Sprite.pack()` synthesised row padding as zeroes because padding "is just
padding". **543 of the 1128 stock sprites store non-zero row padding**, carrying
1020 distinct values. Before the fix, a change-nothing round trip corrupted 48 of
the 69 themeable screens: 21 of 69 survived. After it, all 69 do.

You do not get to decide a byte you cannot explain is meaningless. The whole
architecture is "patch over the original", not "rebuild from understanding", for
exactly this reason (plan §3). The one audited exception is IMAGEWTY, which is
rebuilt from its parsed table *because* the result was proven byte-identical.

## 5. A name is not an address

`boot_pkg_uboot_nor.fex` appears **twice** in the item table, under subtypes
`BOOTPKG-00000000` and `BOOTPKG-NOR00000`. `imagewty.build()` used to key
replacements by name, so it would have silently rewritten a bootloader the caller
never meant to touch. `cardscript.fex` — the SD recovery script — names
`BOOTPKG-NOR00000` specifically, so guessing there breaks a recovery route.

Payloads are indexed by item position. An ambiguous name raises `ValueError`
naming both subtypes. Keep it that way.

## 6. The `data_udisk.fex` partition size must never change

14 614 528 bytes. Its size is declared in three places **outside** the image that
this toolchain does not rewrite: `sys_partition_nor.fex` (`ROOTFS size = 28544`
sectors), `rootfs_ini.tmp` (`size=14272` KB) and `dlinfo.fex` (28 544 sectors).
Change the partition without changing those and the flasher writes a ROOTFS the
flash layout does not describe.

Anything new must come out of the 2 663 808-byte free tail. `build()` raises
`ValueError` naming both declarations; do not add a bypass flag.

## 7. V-sums are always recomputed, never hardcoded

`vsum(partition) = sum of little-endian u32 words mod 2**32`. The flasher checks
them (`efex_verify_transfer_status` in `usbtool.fex`), so a stale V-partition
means a rejected — or worse, half-written — image.

The pairing is read out of `dlinfo.fex` at build time, not baked in. Do not
"optimise" that into a constant table, and never paste a checksum literal into
code or a test.

## 8. Never recommend flashing until `docs/hardware.md` documents a *verified* recovery path

It currently does not. `usbtool.fex` / PhoenixSuit and `cardtool.fex` +
`cardscript.fex` exist in the image — **present is not verified**. Nobody has
restored a unit.

Until QA case 5 (flash the *unmodified* stock image via USB and via SD, device
boots both ways) has actually been performed, flashing anything is forbidden,
including a byte-identical rebuild. Byte-identical tests say the file is right;
they say nothing about whether you can undo a mistake.

Do not soften this, do not offer "it should be safe because", and do not put
flashing steps in a skill.

## 9. `melislzma.compress` does not exist — never pretend firmware code can be repacked

`decompress` is a heuristic and is measurably wrong: it overshoots
`/apps/init.axf` by 30 bytes (2 501 594 vs a declared 2 501 564) and mis-decodes
three files. There is no compressor at all.

So: no patching `init.axf`, no "we can just recompress it". If a task needs it,
say it is blocked and point at `docs/roadmap.md` item 1. `minfs.replace()` could
physically store `init.axf` raw, but whether the loader accepts a
formerly-compressed file stored raw is ⚠️ UNVERIFIED — and that is not a thing to
find out on a device you cannot recover.

## 10. Mark every unverified statement `⚠️ UNVERIFIED`

Exactly that string, in docs, commit messages, and answers. Include the
experiment that would settle it. An unmarked sentence in this repository is a
promise that code was run.

## 11. Golden files in `tests/fixtures/` are never regenerated silently

`tools/mkfixtures.py --update` is only ever run together with an entry in
`docs/findings.md` explaining why the expected value moved, in the same commit.

A fixture that disagrees with `stock/` is either a real regression or a real
finding. Both are worth a paragraph. A silent `--update` is precisely the path by
which a regression reaches the image.

## 12. `stock/` is read-only and irreplaceable

`stock/LTTF133.img` is the pristine vendor image and the reference every
byte-identical test compares against. Never write into `stock/`, never let a
build target it, never `git add` it (it is gitignored, ~57 MB).

`stock/partitions/`, `stock/rootfs/` and `stock/png/` are regenerable from the
`.img` via `tools/unpack.py`. The `.img` itself is not regenerable from anything
in this repository. All output goes to `out/`.

---

## Where things are

| You need | Read |
|---|---|
| what has been proven, and what the plan got wrong | `docs/findings.md` |
| a format's layout | `docs/formats/{imagewty,minfs,datav1,melis-lzma}.md` |
| SoC, partitions, recovery machinery, passwords | `docs/hardware.md` |
| `Config.ini` keys | `docs/config-keys.md` |
| what is deliberately not done yet, and where to start | `docs/roadmap.md` |

## Procedures

Follow these rather than improvising:

* `.claude/skills/unpack-firmware/` — get a `stock/` tree from an image
* `.claude/skills/build-theme/` — PNG → theme → `.img`
* `.claude/skills/verify-roundtrip/` — **mandatory** before any `formats/` commit
* `.claude/skills/reverse-format/` — how to decode something new without guessing

## Code style

Follow `formats/*.py`: a docstring at the top carrying the format layout, a
dataclass per record, few comments in the body. Put the explanation in the
docstring or in `docs/`, not in inline comments.

Tests are mandatory here, not "on request" — a deliberate departure from the
usual rule, because the cost of a regression is a device, not a bug report.
