# Roadmap

Everything the foundation deliberately does **not** do. Plan `F9070W-1` §1 listed
most of these as out of scope; items 2a and 2b came out of `F9070W-2` the same
way. This page turns each into an entry point so a later session does not have to
rediscover where to start.

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

## 2a. Radio audio while CarPlay is on screen — **blocked**

A product requirement, not a format question: play FM while the CarPlay screen is
up, and hand the audio back and forth — start a track in the CarPlay player and
the radio goes quiet, stop it and the radio returns.

**Nobody has run a single experiment for this.** Nothing below was tried on a
device.

**What is already known.** `bRadioSoundAtCarPlay=1` was set and the radio still
did not play — see "Disproven on hardware" in `docs/findings.md`. The refusal
comes from a guard inside `/apps/init.axf`, which rejects the request **by
priority, before the config flag is consulted at all**. The strings, re-located
in `stock/rootfs/apps/init.axf` for this page:

```
0x1a90d9  无效，CarPlay连接中
0x1db471  Priority is low,SourceApp:%s,uiID:%d[%d<%d]
0x1db4d1  Priority is important,SourceApp:%s,uiID:%d[%d<%d]
```

That is where a disassembler would start. So the flag is not the lever. The
two-way hand-off the requirement actually asks for is a further step again: it is
arbitration logic, not a switch.

⚠️ UNVERIFIED, and the reason the item is worth keeping open rather than closing:
the `uiID:%d[%d<%d]` format suggests a numeric priority system that **already
exists**, so the change might be values rather than new logic. That is an
inference from a format string. Nothing has been disassembled.

**What would unblock it** — item 1, then item 2, in that order, and the chain is
strict:

1. Decode the MINFS chunk-table field (roadmap item 1, step 1–2).
2. Make `melislzma.decompress()` exact. Everything downstream needs this: to
   store `init.axf` raw you must first be able to unpack it *exactly*, or you
   write a corrupted binary. There is no compressor at all (`AGENTS.md` rule 9).
3. Choose how to write it back — raw into the free tail, or a real `compress()`.
   Both depend on step 2.
4. Disassemble RISC-V RV64 and find the guard in a 2.5 MB binary. The Chinese
   string is the entry point for finding references to it.
5. Patch, build, differential audit — and then stop, because this is the first
   change that touches **code** rather than data, and the gate at the bottom of
   this page has not moved.

**Honest cost:** estimated at 40–70 hours across three or four sessions, medium
probability of success, and a real risk of an unrecoverable unit. That is an
estimate, not a measurement, and it is the reason the work was deliberately not
started. Coming back to it only makes sense once recovery is proven.

### The cheap experiments — the gate is open, 1–4 not yet run

Configuration-only, each one delivered as a single `Config.ini` through `update/`
and reverted the same way, so the risk is about as low as it gets on this device.
Expectations are low too — the guard is in the code and we know it — but a
negative result here has its own value: it narrows the search for the patching
route, exactly as the `bRadioSoundAtCarPlay` result already did.

**Read the result the right way or do not write it down.** Attempt 0 established
that `Config.ini` is not consulted at every start: the same file gave a different
start-up volume after an ACC cycle than it did right after being applied and
after a Reset Factory (`docs/findings.md`). So observe immediately after the
config is applied, or force a Reset Factory first. A negative result taken after
an ACC cycle alone means nothing — the file may simply never have been re-read.

Change one thing at a time. After each: connect CarPlay, start a video, switch
the radio on, and write down **what actually happened** — not "did not work", but
whether the radio stayed silent, the CarPlay audio disappeared, a message
appeared on screen, or the source switched.

| # | Change | Hypothesis under test |
|---|---|---|
| **0** | add `bMaxVolumeAsDefVolume=1` to `[STARTUP]` | **Done — positive.** The unit came up at 20 instead of 5, so a key absent from the stock file *is* read. That opens 2–4. It also exposed the re-read behaviour above. ⚠️ UNVERIFIED that the key means "use the maximum as the default" rather than something that merely happens to look like it. Reverted; not in `themes/config/Config.ini` |
| 1 | `bRadioSoundAtCarPlay=1` | Control. Reproduce the known negative result, to confirm the setup measures what it claims to |
| 2 | `bAirPlayBackground=1` in `[LINK]` | The most promising. Radio and media each have a background flag in the file (`bRadioBackgroundRun=1`, `bMediaBackgroundPlay=0`); CarPlay's equivalent exists only in `init.axf` |
| 3 | `bAudioOutputAutoCtrl=0` + `bRadioSoundAtCarPlay=1` | Whether automatic output control is what grabs the source |
| 4 | `bLinkVol=1` + `linkVol=0` | Silence CarPlay instead of arguing with the arbiter, leaving the radio as the only source |

Verified for this page: `bMaxVolumeAsDefVolume`, `bAirPlayBackground`,
`bAudioOutputAutoCtrl`, `bLinkVol` and `linkVol` all appear as strings in
`init.axf` and **none of them is a key in `Config.ini`** (the file's only
`linkVol`-like key is `linkVolGain`). Attempt 0 was the gate on the other four —
if keys that were not in the stock file were ignored, 2–4 would have been
impossible by construction. They are not: one such key was read and acted on.

Attempt 0 does **not** settle item 2b below. A key and a section are read by
different code, and only the key case was observed. What it does is make the
`[EUROPE]` attempt worth the power cycle.

**Stop after four.** This is a check of cheap hypotheses, not a blind search; a
fifth attempt costs more than it can tell you.

---

## 2b. FM presets for the EUROPE zone — **pending, needs hardware**

Wanted on the first FM page: 102.6, 99.8, 90.9, 91.3, 90.5, 92.0. FM only — AM
was explicitly not asked for.

**Nothing has been done.** `themes/config/Config.ini` contains **no `[EUROPE]`
section**, on purpose: writing one means asserting what the nine fields of a band
plan mean, and no field has ever been changed and observed. See
`docs/config-keys.md` for the two ⚠️ UNVERIFIED questions this rests on — whether
a zone-named section is read at all, and what the nine fields are.

The odds improved: item 2a's attempt 0 showed that a key the stock file never had
is read and acted on, so the parser is not restricted to what it shipped with.
That does not carry over to sections — different code — but it makes this worth
the power cycles.

It cannot be done by reasoning. The procedure is a short series of cheap,
revertible deliveries, each one `Config.ini` alone through `update/`, each
costing a power cycle (budget ~20 minutes per round).

**Before every reading: Reset Factory, or read the result immediately after the
config is applied.** An ordinary ACC cycle can show the stored settings rather
than the file — that is how attempt 0 gave 20, then 5, then 20 from one
unchanged file. A preset that "did not appear" after an ACC cycle has not been
disproved, only not re-read.

1. **Is the section read?** Add `[EUROPE]` as a copy of `[AMERICA2]`, changing
   only field 2 of `FM1` to `10260` — 102.6 MHz is a real station, so the result
   is audible as well as visible. Look at the first preset cell.
   * changed → the section is read *and* field 2 is the first preset; go to 3
   * unchanged → go to 2
2. **Separate "section ignored" from "field 2 is not a preset."** Put `FM1`
   back and change field 1 to `8700` instead (87.0 MHz, the usual European band
   floor).
   * the band's lower limit moves → the section **is** read, and fields 2–7 mean
     something other than presets. Keep going one field at a time
   * nothing moves → the section is **not** read. Go to 5
3. **Set all six.** Under the confirmed reading:

   ```
   [EUROPE]
   FM1=8700,10260,9980,9090,9130,9050,9200,10,10
   ```

   | Cell | Frequency | Value |
   |---|---|---|
   | 1 | 102.6 | `10260` |
   | 2 | 99.8 | `9980` |
   | 3 | 90.9 | `9090` |
   | 4 | 91.3 | `9130` |
   | 5 | 90.5 | `9050` |
   | 6 | 92.0 | `9200` |

   Leave `FM2` and `FM3` stock. Do not add `AM1`/`AM2`.
4. Record field → meaning in `docs/findings.md` **with the proof**: what was
   typed in and what appeared on screen. Drop `⚠️ UNVERIFIED` in
   `docs/config-keys.md` only from the fields actually measured — not from all
   nine.
5. **If a zone-named section turns out not to be read**, write that down as a
   disproof and the requirement moves into item 2a's dependency chain — the
   defaults would then have to come from somewhere inside `init.axf`, needing the
   same patching route as the CarPlay guard (⚠️ UNVERIFIED, that is where they
   would be looked for, not where they have been found). That is an acceptable
   outcome, not a failure.

Attempt 0 of item 2a has been run and came back positive, so there is no cheaper
question left to ask first — start at step 1.

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

Largely answered by accident: a hand-edited `Config.ini` — two values changed and
one byte shorter than stock — was delivered through `update/` and **applied**,
both keys taking effect (`docs/findings.md`). So either there is no checksum, or
nothing checks it on this path.

⚠️ UNVERIFIED that this generalises. One file, edited in place, staying the same
length to within a byte, proves nothing about a file that grows, gains a section
or reorders keys. And the `update/` route is not the only reader. Until the
config reader is disassembled the safe reading is: small in-place value edits are
demonstrably tolerated, everything else is untested.

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
