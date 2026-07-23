# Findings

The journal. Every entry says what was measured and what proves it. Where the
original plan (`F9070W-1`) said something different, the plan's claim is quoted
next to the measurement — the code and the tests win.

Nothing here is a belief. Anything believed but not demonstrated is marked
`⚠️ UNVERIFIED` with the experiment that would settle it.

---

## Disproven on hardware

### `bRadioSoundAtCarPlay=1` does not work

Setting `bRadioSoundAtCarPlay=1` in `[RADIO]` was tested on the device. Radio
audio still does not play while CarPlay is connected.

The cause is a guard in `/apps/init.axf`, not the config. Both strings are
present in the decompressed binary:

```
无效，CarPlay连接中
Priority is low,SourceApp:%s,uiID:%d[%d<%d]
Priority is low,TopApp:%s,uiID:%d[%d<%d]
Priority is important,SourceApp:%s,uiID:%d[%d<%d]
```

(The first is at byte 1 741 017 of `stock/rootfs/apps/init.axf`; the rest come
out of `strings -a`.)

So the audio-source arbitration refuses the request by priority before the config
flag is ever consulted. Making this work means patching `init.axf`, which means
melis-lzma has to become exact — see `docs/formats/melis-lzma.md`. Do not
re-litigate this by flipping the config again.

---

## Confirmed on hardware

Reported by the developer from direct observation on the device. Observation on
real hardware outranks anything read out of the binary — but it establishes only
what was actually seen, and the limits are recorded with each entry.

### `stalogo1.jpg` is the boot logo

Seen on screen during startup. Two byte-identical copies exist:

```
/res/stalogo1.jpg            44133 B  uncompressed  800x480 RGB JPEG
/apps/Logo/stalogo1.jpg      44133 B  uncompressed  same sha256
```

⚠️ **UNVERIFIED which copy is read.** The two are byte-identical, so seeing the
image on screen cannot distinguish them. Replace **both**. Settling it means
writing two *different* images and seeing which one appears.

It is a plain JPEG in the MINFS tree, not a DATAV1.0 sprite, so `tools/build.py`
does not touch it — patch it with `minfs.replace` directly.

### The recovery button is not a rollback

The button restores settings to the last state that was **flashed**, not to a
factory state baked into the SoC. Flash a modified `Config.ini` from USB and the
button afterwards restores *that* config.

This matters more than it looks: **the recovery button is not a safety net.**
A bad image cannot be undone with it, because it would restore the bad image's
own settings. Nothing in `docs/hardware.md`'s recovery section is replaced by it.

### A toolchain-built full image flashes and boots

The headline result of the project. A `LTTF133.img` produced by
`imagewty.build()` was flashed from a USB `update/` folder; the device came back
up with no regressions.

The image differed from stock only in `/res/stalogo1.jpg` and
`/apps/Logo/stalogo1.jpg` (a replaced 800x480 JPEG), plus the recomputed
`Vdata_udisk.fex`. It was audited before flashing, and the audit is the reason
this was a reasonable thing to do:

```
відмінних діапазонів: 367, всього 87276 B
  data_udisk.fex     366 ranges, 87272 B
  Vdata_udisk.fex      1 range,      4 B
header 0x00..0x400 identical, item table identical, other 23 partitions identical
files 257 -> 257, none moved, only the two JPEGs changed
sprites 1128 -> 1128, 0 changed
69 compressed files: 0 changed, init.axf byte-identical
free tail 2663808 -> 2663808, V-sum recomputed and correct
```

What this establishes:

- the flasher **accepts `imagewty.build()` output** — the two-region padding, the
  recomputed `offset`/`stored_len`/`length`/`image_size`, and the V-sum algorithm
  are all sufficient, not merely self-consistent;
- `vsum` is the **only** checksum that matters for `data_udisk.fex`. Had there
  been another integrity field anywhere in the header, table or partition, this
  image would have been rejected;
- the whole chain — `minfs.replace` → `imagewty.build` → flash → boot — is real.

What it does **not** establish: that a *bad* image can be undone, that sprite
edits specifically are safe (this image changed no sprite — see below), or that
the unit survives repeated cold starts (plan §8 case 8 is still unrun).

The one remaining difference between this and a sprite theme is
`datav1.rebuild()`, which is covered by round-trip tests over all 1128 stock
sprites and by the byte-identical whole-image test.

### The device updates itself from a USB stick

An `update/` folder on a USB stick is picked up on its own and the unit reboots
by itself. Both granularities are confirmed: **individual files** (`Config.ini`,
the boot logo) and a **full `LTTF133.img`**. That gives a graduated risk ladder —
a single cosmetic file is a far smaller step than rewriting `data_udisk.fex`
whole — but all three rungs now work.

⚠️ **UNVERIFIED: whether this survives a broken image.** The updater with the
progress UI lives in `/apps/init.axf` — the very partition a theme rewrites —
and its screens are in the binary (`SetupUpdate`, `SetupOtaUpdate`,
`ViewShowSliderUpdateProgress`, `UpdateMcu.bin`). If the app does not boot, that
updater is gone with it. The separate u-boot-level path (`usb update probe`,
`usb_update_efex`, `pburn` in `u-boot_nor.fex`) is USB-gadget flashing over a
cable and does not depend on the app — but it has never been exercised.

---

## `Config.ini`: measured, patched, not delivered

### The file itself

Re-measured on the stock partition rather than taken from the plan:

```
minfs entry /apps/Config.ini   offset 4962108  stored 5761  compressed False
partition bytes == stock/rootfs/apps/Config.ini == tests/fixtures/Config.ini : True
5761 bytes, 402 CRLF, 0 bare LF
29 section lines, 311 key/value lines, 63 blank lines
configparser: 29 sections, 311 keys
[BACKLIGHT] backLightMode = 0
[STARTUP]   startUpDefVolume = 10, startUpMinVolume = 5, startUpMaxVolume = 20
[RADIO]     radioArea = 6, bRadioSoundAtCarPlay = 0, bRadioBackgroundRun = 1
zone-named sections present: ['AMERICA2', 'Brazil']   'EUROPE' in sections: False
```

Every one of those agrees with what the plan claimed, which is worth saying only
because the rule is to re-run it rather than repeat it.

`init.axf` carries eleven zone names in a contiguous run of 8-byte NUL-terminated
slots at `0x1f3569`, `CHINA … KOREA`, listed slot by slot in
`docs/config-keys.md`. ⚠️ UNVERIFIED that a name's position in that run is the
value `radioArea` takes — a run of strings is not an indexed array, and no code
was disassembled. Settling it needs the reader out of `init.axf`, i.e. roadmap
item 1 first.

### A golden fixture for it, and why rule 11 has nothing to say

`tests/fixtures/Config.ini` now pins the stock file so a clone without `stock/`
can still assert against it. Rule 11 governs *regenerating* a fixture — an
expected value that moved is either a regression or a finding, and either needs a
paragraph. This fixture is new: no existing expected value changed, and the bytes
were measured identical to both the partition slice and the unpacked tree before
being committed. There is nothing to explain, which is the point of writing it
down.

### What `tools/patchfile.py` proves

Feeding the stock file back in unchanged reproduces the vendor image exactly:

```
/apps/Config.ini  5761 -> 5761 bytes, in place;  free tail 2663808 -> 2663808
cmp out/LTTF133.img stock/LTTF133.img  ->  BYTE-IDENTICAL
```

Feeding in `themes/config/Config.ini` — the two-line change — moves exactly what
it should and nothing else. Full differential audit, re-run for this entry:

```
payloads changed: 2 of 25 -> data_udisk.fex (DATA_UDISK_FEX00),
                              Vdata_udisk.fex (VDATA_UDISK_FEX0)
partition size   14614528 -> 14614528
rootfs files     257 -> 257,  changed 1 -> ['/apps/Config.ini'],  moved 0
compressed blobs 69,   changed 0,   init.axf identical: True
screens 75, sprites 1128 -> 1128, changed 0
free tail 2663808 -> 2663808
vsum(new partition) = 0x39249d4f  ==  Vdata_udisk.fex in the new image
```

The two-key edit makes the file 5761 → 5760 bytes, so it stays in its stock slot
and no other entry moves. The V-sum is recomputed and matches, as rule 7 requires.

This is the same shape of audit that preceded the flash recorded above under
"Confirmed on hardware", one layer narrower: that image changed two JPEGs, this
one changes one text file.

### Still open: the whole hardware half

Nothing in this work was delivered to the device and nothing was flashed. What
that leaves unanswered:

* **`startUpDefVolume=5`.** ⚠️ UNVERIFIED. `backLightMode=2` is confirmed —
  by the developer, from direct observation, and it is the *only* hardware fact
  in this entry. The volume key rides along in the same file and has been
  observed by nobody. What would settle it: `Config.ini` alone through `update/`,
  a complete power cut, then read the volume at start.
* **Whether the parser reads a section named after the active zone**, i.e.
  whether an added `[EUROPE]` is seen at all. ⚠️ UNVERIFIED. No `[EUROPE]`
  section was added to `themes/config/Config.ini`, deliberately — adding one and
  writing down what its nine fields mean without having watched a screen is
  precisely the guess rule 1 forbids.
* **The nine fields of `FM1`/`AM1`.** ⚠️ UNVERIFIED, and specifically *not*
  decoded. There is a hypothesis (field 1 = band floor, 2–7 = six presets,
  8–9 = steps) and it is written down as a hypothesis in `docs/config-keys.md`.
* **Whether the parser reads a key that was absent from the stock file.**
  ⚠️ UNVERIFIED, and it is the cheapest question in the whole area because one
  meta-test answers it for both the `[EUROPE]` section and every code-only key.
  The procedure is in `docs/roadmap.md`.
* **Radio audio while CarPlay is connected.** No new experiment was run. The
  known negative result stands unchanged — see "Disproven on hardware" above for
  `bRadioSoundAtCarPlay=1` and the `init.axf` guard behind it. The requirement is
  now carried as a blocked item in `docs/roadmap.md`.

---

## Corrections to the plan's §2

### 1. IMAGEWTY padding is two regions, not one

**Plan said:** "IMAGEWTY: 25 partitions, alignment 1024, padding is the byte
`0xCD`", proved by "rebuild with `0xCD` → BYTE-IDENTICAL REBUILD: True".

**Measured:** there are two fill regions per item — zeroes from `offset+length`
to `offset+stored_len` (where `stored_len == align(length, 16)`), then `0xCD` up
to the next 1024 boundary. Whole-image filler histogram over all 25 items:

```
{0x00: 70, 0xCD: 8128}
```

Filling both regions with `0xCD` does not reproduce the image.

Pinned by `test_filler_is_zeroes_up_to_stored_len_then_cd_up_to_the_boundary` and
`test_whole_image_filler_histogram_is_seventy_zeroes_and_8128_cd`.

⚠️ UNVERIFIED (carried over from the plan): whether `0xCD` is a stable vendor
convention or an artefact of this one build. Needs a second vendor image.

### 2. Sprite record headers come in two sizes

**Plan said:** "bytes `+0x18..0x20` of the sprite header are non-zero in 14
screens, purpose unknown".

**Measured:** the distinction is the **header size**, and the tail never varies.

```
header sizes {24: 788, 32: 340}
screens per header size {24: 55, 32: 14}, overlap 0
32-byte tails seen: {b'\x01\x00\x00\x00\x00\x00\x00\x00'}
```

788 sprites across 55 screens have a 24-byte header and therefore no
`+0x18..0x20` bytes at all. 340 sprites across 14 screens have a 32-byte header
whose `+0x18..0x20` is *always* `01 00 00 00 00 00 00 00`. No screen mixes the
two. Pinned by `test_stock_header_sizes_split_55_and_14_screens`.

⚠️ UNVERIFIED: what the 32-byte variant signals. A constant value carries no
information; a second firmware image with a different value would.

### 3. `datav1.Sprite.pack()` used to zero the row padding — a real bug

**Plan said:** nothing; it assumed the existing `datav1` was "proven".

**Measured:** 543 of the 1128 stock sprites store **non-zero** row padding,
carrying 1020 distinct padding values, and the old `pack()` replaced all of it
with zeroes. Re-running the pre-fix behaviour as a simulation over the stock tree:

```
zeroed padding: 21/69 screens survive, 543/1128 sprites corrupted
```

A "change nothing" round-trip silently altered 48 of the 69 themeable screens.

Fixed in `abd3cd3`: `pack()` lifts the padding out of the sprite's own stored
buffer instead of synthesising it. `pack(pixels()) == decode()` now holds for all
1128 sprites (`test_no_stock_sprite_loses_its_row_padding`, 0 lossy).

This is what made the end-to-end "stock PNGs through the whole chain change zero
bytes" test achievable at all.

> Note on numbers: the implementation notes reported this as "11 of 36 screens
> reproduced before the fix, 36 of 36 after". That does not reproduce here. The
> measurement re-run for this document is **21 of 69** themeable screens
> surviving before the fix (75 screens exist, 69 carry at least one sprite, 6 are
> pure layout). The 543/1128 sprite figure does reproduce exactly.

### 4. `build()` was keyed by partition name, and two items share a name

**Plan said (§4 T08):** `build(image, replace: dict[str, bytes])` — a name-keyed
dict, silently assuming names are unique.

**Measured:** `boot_pkg_uboot_nor.fex` appears **twice** in the item table, under
subtypes `BOOTPKG-00000000` (offset 334 848) and `BOOTPKG-NOR00000` (offset
662 528). The payloads are identical today; the table entries are not.

Fixed in `ba46963`: payloads are indexed by item position, and replacing an
ambiguous name raises `ValueError` naming both subtypes rather than guessing.
This matters concretely — `cardscript.fex` (the SD recovery script) names
`BOOTPKG-NOR00000` specifically, so a wrong guess breaks a recovery route.

Pinned by `test_exactly_one_item_name_is_used_twice`,
`test_the_two_uboot_package_items_are_distinct_partitions` and
`test_replacing_an_ambiguous_name_raises_and_names_both_subtypes`.

### 5. The MINFS entry of a compressed file carries the real chunk table

**Plan said:** MINFS entry `+0x10` is `u32 name_len`; melis-lzma chunk boundaries
are recovered by scanning for the `5d 00 80 00 00` signature.

**Measured:** `+0x10`'s low 16 bits are the name length in all 257 entries, but
in exactly **69** entries the value exceeds `0x100` — and 69 is exactly the number
of compressed files. Those entries are oversized (`entry_size` 188..348 instead of
`20 + align4(namelen)`), and the surplus is always a multiple of 32 bytes: 5, 6 or
10 records.

The first u32 of each 32-byte record is an offset into the compressed blob. For
**66 of 69** files those offsets are exactly what the signature scan finds; the 3
that disagree are precisely the files the scan gets wrong:

| file | table | signature scan |
|---|---|---|
| `/mod/cedar/arec.plg` | `0, 2648, 2976, 3112, 0, 3144` | `0, 2976` |
| `/mod/charset.mod` | `0, 32, 936, 120740, 120740, 120740` | `32, 936` |
| `/mod/slib.mod` | `0, 216, 6996, 7564, 7564, 7564` | `216` |

`/apps/init.axf`'s entry literally contains `904944` and `1075560` — exactly the
boundaries `melislzma._chunk_bounds` rediscovers by scanning.

This is a **lead, not a decoded format.** ⚠️ UNVERIFIED: the meaning of every
column after the first. Columns 2 and 3 look like compressed/uncompressed chunk
sizes, but for `init.axf` they sum to 2 501 048 rather than the declared
2 501 564, so that reading is wrong or incomplete. Settling it needs the loader's
reader disassembled out of `init.axf`, or a second firmware image to diff.

Pinned by `test_compressed_entries_carry_an_oversized_record`.

### 6. `minfs._read_entry` is accidentally quadratic

**Plan said:** nothing; `minfs` was listed as "proven, tests only".

**Measured:** because `_read_entry` takes the whole `+0x10` u32 as a name length,
it slices up to `0x0140_0000` (20 MB) out of the partition before `split(b'\0')`
cuts it back. The parse is *correct* — names come out right — but one
`minfs.files()` call on the stock partition costs **1.38 s**, and `replace()`
calls it twice. That is why the stock suite runs for minutes.

Masking the field to its low 16 bits fixes finding 5's layout question and this
performance problem in one change. Not done yet — it belongs with the melis-lzma
work.

### 7. Pillow has a `BGR;16` decoder but no encoder

**Plan said:** nothing; PNG export/import was assumed symmetric.

**Measured:** `Image.new('RGB',(1,1)).tobytes('raw','BGR;16')` raises
`ValueError`, so `tools/build.py` packs RGB565 by hand (`rgb_to_565`, plus the
`_R5` / `_G6` quantisation tables). The packing is asserted to be the exact
inverse of Pillow's decoder over **all 65 536 code points**
(`test_rgb565_packing_inverts_the_decoder_for_every_code_point`) and over **all
65 depth-2 sprites** in the firmware
(`test_every_depth_two_sprite_survives_the_png_detour_with_zero_loss`).

The quantisation is lossy in principle — an 8-bit value the decoder never emits
would not survive — but every value in a stock-exported PNG does come out of the
decoder, so the **measured loss on stock content is zero**.
`test_pillow_still_has_no_bgr16_encoder` exists so the hand-rolled packer can be
deleted the day Pillow grows an encoder.

### 8. `vsum` rejects a short tail instead of ignoring it

**Plan said (§4 T07):** "a tail shorter than 4 bytes is ignored (stock partitions
have none — pin it with an assert)".

**Landed:** `vsum()` raises `ValueError('partition length is not a multiple of
4')`. Deliberate divergence: no stock partition has such a tail, so the branch
would never run on real data, and silently dropping bytes from a checksum is
exactly how a corrupted partition passes verification. Failing loudly costs
nothing and catches a caller who sliced a partition wrong.

Pinned by `test_vsum_rejects_a_length_that_is_not_a_multiple_of_four`.

### 9. V-partition pairing is derived, not hardcoded

**Plan said:** listed the two pairs as facts
(`DATA_UDISK_FEX00↔VDATA_UDISK_FEX0`, `MELIS_PKG_NOR_FE↔VMELIS_PKG_NOR_F`).

**Landed:** `imagewty._v_pairs()` reads them out of `dlinfo.fex` at build time, so
an image that pairs differently is handled without a code change. The two
expected pairs are asserted as a *fact about this image*, not baked into the
builder (`test_dlinfo_pairs_the_two_checksummed_partitions`).

`dlinfo` also independently corroborates the ROOTFS size: the `ROOTFS` record
declares 28 544 sectors, x 512 = **14 614 528** = exactly the `length` of
`data_udisk.fex`, which is also what `sys_partition_nor.fex` (`size = 28544`
sectors) and `rootfs_ini.tmp` (`size=14272` KB) say. Three independent
declarations, one number.

Note that `dlinfo`'s `size_sectors` is a *slot* size, not a payload length: the
`bootA` record declares 3200 sectors = 1 638 400 bytes for a
`melis_pkg_nor.fex` payload of 1 589 248. The ROOTFS match is exact only because
that partition fills its slot.

---

## Smaller corrections

### `free_offset` is not monotonic

**Plan said (§6):** "`free_offset` monotonic".

**Measured:** it is `align16(max(offset + stored))`, so shrinking whichever file
currently sits highest lowers it again. Pinned as-is by
`test_free_offset_grows_with_the_relocated_block_but_is_not_monotonic`, because
relocation depends on the actual behaviour, not the described one.

### The V-partitions are 4 bytes, not 16

**Plan said:** "`data_udisk.fex` is the second-to-last partition, followed only by
`Vdata_udisk` (16 B)".

**Measured:** `length = 4`, `stored_len = 16`. The 16 is the `align(4, 16)` slot,
zero-filled — see correction 1.

### 75 screens, but only 69 are themeable

Six of the 75 `/apps/Data/*.data` screens contain no sprite at all (pure layout),
so a theme can never reach them and `build_screens` never rewrites them. The
plan's "75/75" round-trip figure counts screens that rebuild identically, which
is a different measurement from screens a theme can touch.

---

## Confirmed as stated in the plan

Re-measured for this document; the plan was right about these.

| Claim | Measurement |
|---|---|
| SoC is Allwinner F133/D1s, RISC-V | `u-boot_nor.fex` strings: `U-Boot 2018.07 ... Allwinner Technology`, `Bad Linux RISCV Image magic!`, `allwinner,riscv`, `allwinner,sun20iw1p1-pinctrl` |
| 25 partitions, 1024-byte alignment | `imagewty.parse` on the stock image; every offset ≡ 0 mod 1024 |
| No checksum in the header or item table | `build(img, {})` is byte-identical without computing any CRC |
| V-sum = sum of LE u32 words mod 2^32 | `Vdata_udisk = 0x1e3c76a1`, `Vmelis_pkg_nor = 0x814cb3db`, both match |
| `data_udisk.fex` at offset `0x378000` | 3 637 248 = `0x378000`, and it is the second-to-last item |
| ROOTFS size fixed at 28544 sectors / 14272 KB | `sys_partition_nor.fex` and `rootfs_ini.tmp`, both = 14 614 528 B |
| MINFS: 257 files, 188 uncompressed | `minfs.files()`: 257 total, 188 raw, 69 compressed |
| All 75 `.data` screens stored uncompressed | `test_every_data_screen_is_stored_uncompressed` |
| Free tail = 2 663 808 bytes | `free_offset = 11 950 720`, partition 14 614 528 |
| 1128 sprites, 31.6 Mpx, depths 4/3/2 | `{4: 132, 3: 931, 2: 65}`, `stride = align4(w * depth)` for all |
| Stock PNGs back through the pipeline gives 0 changed bytes | `test_stock_pngs_through_the_whole_chain_change_zero_bytes` |
| melis-lzma overshoots init.axf by 30 bytes | 2 501 594 vs a declared 2 501 564; bounds `0, 904944, 1075560` |
| The compressed extensions are drv/mod/plg/axf | `rootfs_ini.tmp` `[COMPRESS_EXT] count=4` |
| 27 languages in `apps/Language/*.txt` | UTF-16LE TSV with a BOM, 29 columns: `//`, 原始, then 27 languages; 13 files |

---

## Open, unverified

* **The recovery path.** Not verified on hardware. Flashing is forbidden until it
  is. See `docs/hardware.md`. This is the single blocking item.
* **`0xCD` stability** across vendor builds — needs a second image.
* **Whether the loader accepts a formerly-compressed file stored raw.** `init.axf`
  would fit raw with ~1.3 MB of the free tail to spare, but nothing proves the
  loader tolerates it. Needs a device with a confirmed recovery path.
* **`Config.ini` checksum algorithm** — unknown; assume a hand-edited file may be
  rejected.
* **Whether `Config.ini`'s parser reads a section or a key that the stock file
  does not contain** — one meta-test settles both; see the `Config.ini` section
  above and `docs/roadmap.md`.
* **The nine fields of the per-zone `FM1`/`AM1` band plans**, and whether a
  zone's position in `init.axf`'s name run is the value of `radioArea`.
* **The 32-byte chunk-table record fields** — see correction 5.
* **The 32-byte sprite header's meaning** — see correction 2.
* **The DATAV1.0 layout section** — not decoded at all; copied verbatim.

## Rules that came out of this

* Never zero or "normalise" a byte you cannot explain. Corrections 1, 2 and 3 are
  all the same mistake in three places.
* A name is not an address (correction 4).
* When the plan and the measurement disagree, write the measurement down here
  before changing the code.
* Golden fixtures are never regenerated silently — a `tools/mkfixtures.py
  --update` needs an entry on this page explaining why the expected value moved.
