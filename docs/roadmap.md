# Roadmap

Everything the foundation deliberately does **not** do. Plan `F9070W-1` §1 listed
these as out of scope; this page turns each into an entry point so a later
session does not have to rediscover where to start.

The foundation depends on none of them. They can be picked up in any order,
except where noted.

Before touching anything here, read `AGENTS.md` and `docs/findings.md`.

---

## 1. melis-lzma: make `decompress()` exact — start here

**Why first:** it unblocks item 2 (patching `init.axf`), and it comes with a free
performance fix.

**The lead is concrete.** The chunk table is already in the MINFS directory entry
of every compressed file — we do not have to find it, only decode it. See
`docs/formats/melis-lzma.md` and finding 5 in `docs/findings.md`.

Steps:

1. Mask `minfs` entry `+0x10` to its low 16 bits for the name length. This also
   removes the ~1.4 s cost of every `minfs.files()` call (finding 6) — the stock
   test suite drops from minutes to seconds as a side effect.
2. Parse the 32-byte records that follow the padded name. Their count is
   `(entry_size - 20 - align4(namelen)) / 32`; measured values are 5, 6 and 10.
3. Drive `decompress()` from the table's offsets instead of the signature scan.
   Success criteria, both already pinned as the *current* behaviour in
   `tests/test_melislzma.py`: `/apps/init.axf` comes out at exactly 2 501 564
   bytes instead of 2 501 594, and the three files the scan currently gets wrong
   (`/mod/cedar/arec.plg`, `/mod/charset.mod`, `/mod/slib.mod`) decode correctly.
4. Only then consider `compress()`. Writing a stream means writing a matching
   table back into the MINFS entry, and the entry's remaining columns are still
   ⚠️ UNVERIFIED.

**Estimated blast radius:** `formats/minfs.py`, `formats/melislzma.py`,
`tests/test_minfs.py`, `tests/test_melislzma.py`. Nothing on the theming path.

---

## 2. Patch `init.axf` (APS/Band → radio, and the CarPlay audio guard)

**Blocked by item 1.** Also blocked by hardware recovery — see
`docs/hardware.md`.

`bRadioSoundAtCarPlay=1` was tested and does not work; the guard lives in the
binary (`无效，CarPlay连接中`, `Priority is important/low,SourceApp:%s,uiID:%d[%d<%d]`).
See the "Disproven on hardware" section of `docs/findings.md`.

Note `minfs.replace()` can already write a raw `init.axf` back — it fits in the
free tail with ~1.3 MB to spare — but ⚠️ UNVERIFIED whether the loader accepts a
formerly-compressed file stored raw. Do not find out on a device you cannot
recover.

---

## 3. Decode the `DATAV1.0` layout section

Needed to move or remove a control — for example the button drawn over CarPlay.

Entry point: `formats/datav1.py`. The header is understood up to `0x64` (magic,
header size, layout size, screen width/height, window count, window name in
UTF-16LE). Everything after that is copied verbatim by `rebuild()` and is
undecoded.

Method (per `.claude/skills/reverse-format/`): start from the smallest screens.
`tests/fixtures/black.data` and `wallpaper.data` are 592 bytes with zero sprites
— pure layout — which makes them the ideal minimal specimens. `tipbox.data`
(1068 B) is the next step up.

The non-negotiable acceptance test is the one that already exists: after any
change, `datav1.rebuild(d)` must stay byte-identical on all 75 stock screens.

---

## 4. MINFS writer — creating new files and directories

Today `minfs.replace()` can only overwrite an existing entry (in place, or
relocated into the 2 663 808-byte free tail). Adding a file means growing a
directory table, which moves every entry after it.

Needed for a new UI set (`apps/UI3/`). Constraint that does not move: the ROOTFS
partition is fixed at 14 614 528 bytes (three independent declarations, see
finding 9), so anything new has to come out of the free tail.

Entry point: `formats/minfs.py`, plus the regression in `tests/test_minfs.py`
that asserts a patch moves no other entry — a writer has to keep that property
explicit rather than accidental.

---

## 5. `Config.ini` checksum

⚠️ UNVERIFIED whether the file is checksummed at all, and by what algorithm. Until
it is settled, a hand-edited `Config.ini` may be rejected or may break boot, so
nothing in this toolchain writes it.

Entry points: `docs/config-keys.md` for the full key inventory (311 keys present,
36 more that exist only as defaults in `init.axf`), and the config reader inside
`init.axf` — which needs item 1 first to disassemble cleanly.

---

## 6. The `sunxi-package` container in `melis_pkg_nor.fex`

1 589 248 bytes, magic `sunxi-package` at offset 0. Never opened. It holds the
Melis kernel package; the ROOTFS is a separate partition, so nothing on the
theming path needs it.

Entry point: `stock/partitions/melis_pkg_nor.fex`. Note that changing it means
recomputing `Vmelis_pkg_nor.fex` — `imagewty.build()` already does that
automatically when the partition appears in `replace`.

---

## 7. Font `apps/font22.sft`

Undecoded. Needed for any glyph the stock font lacks — which is what blocks
several of the 27 UI languages from rendering usefully.

Entry point: `stock/rootfs/apps/font22.sft`.

---

## 8. Translations — `apps/Language/*.txt`

13 files, UTF-16LE TSV with a BOM. 29 tab-separated columns: `//`, `原始`
(original), then 27 languages (English, Simplified/Traditional Chinese, French,
German, Arabic, Italian, Japanese, Portuguese, Russian, Spanish, Uyghur, Hebrew,
Persian, Brazilian, Polish, Turkish, Czech, Korean, Indonesian, Thai, Ukrainian,
Bulgarian, Greek, Vietnamese, Dutch, …). `Bt.txt` is 52 lines.

These are plain text files stored raw in MINFS, so `minfs.replace()` handles them
today — the only real work is the encoding discipline and, for a *longer*
translation, checking the layout still fits.

Related: `supportLanguage=34052091` and the code-only `supportLanguage2` in
`Config.ini` presumably select which of the 27 are offered — ⚠️ UNVERIFIED.

---

## The gate on all hardware work

Plan §12 open question 1 is still open: **the recovery path is not verified.**
Until someone has restored a device via PhoenixSuit *and* via SD card, no built
image goes near hardware, however confident the byte-identical tests look. See
`docs/hardware.md`.
