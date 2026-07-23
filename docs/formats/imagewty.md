# IMAGEWTY

The outer container of `LTTF133.img`. Allwinner's PhoenixSuit / LiveSuit image
format, header version `0x0300`. Code: `formats/imagewty.py`. Tests:
`tests/test_imagewty.py`.

## Layout

```
0x00   "IMAGEWTY"
0x08   header_version (0x0300)
0x0c   header_size (0x60)
0x18   image_size            -- rewritten by build()
0x3c   num_files (25)
0x400  item table, 1024 bytes per entry
```

Item entry:

```
0x00   filename_len (256)
0x04   entry_size (1024)
0x08   maintype[8]
0x10   subtype[16]
0x20   unknown            -- carried over verbatim
0x24   filename[256]
0x124  stored_len, pad, length, pad, offset   (5 x u32; both pads carried over)
```

There is **no checksum in the header or the item table.** That is not an
assumption: `build()` reassembles the whole image from the parsed table and the
result is byte-identical to the vendor file, which no CRC-bearing format would
allow (`test_build_without_changes_is_byte_identical`).

## The 25 stock partitions

`name / maintype / subtype / offset / length`, as printed by
`imagewty.parse(open('stock/LTTF133.img','rb').read())`:

| name | maintype | subtype | offset | length |
|---|---|---|---:|---:|
| sys_config_nor.fex | COMMON | SYS_CONFIG100000 | 26624 | 69766 |
| config_nor.fex | COMMON | SYS_CONFIG_BIN00 | 97280 | 49152 |
| split_xxxx.fex | COMMON | SPLIT_0000000000 | 146432 | 512 |
| sys_partition_nor.fex | COMMON | SYS_CONFIG000000 | 147456 | 3223 |
| sunxi.fex | COMMON | DTB_CONFIG000000 | 151552 | 76800 |
| boot0_nor.fex | 12345678 | 1234567890BNOR_0 | 228352 | 49152 |
| boot0_card.fex | 12345678 | 1234567890BOOT_0 | 277504 | 57344 |
| boot_pkg_uboot_nor.fex | 12345678 | BOOTPKG-00000000 | 334848 | 327680 |
| boot_pkg_uboot_nor.fex | 12345678 | BOOTPKG-NOR00000 | 662528 | 327680 |
| u-boot_nor.fex | 12345678 | UBOOT_0000000000 | 990208 | 311296 |
| fes1.fex | FES | FES_1-0000000000 | 1301504 | 29600 |
| usbtool.fex | PXTOOLSB | XXXXXXXXXXXXXXXX | 1331200 | 154112 |
| usbtool_crash.fex | PXTOOLCH | XXXXXXXXXXXXXXXX | 1485824 | 125952 |
| aultools.fex | UPFLYTLS | XXXXXXXXXXXXXXXX | 1611776 | 165006 |
| aultls32.fex | UPFLTL32 | XXXXXXXXXXXXXXXX | 1777664 | 150834 |
| cardtool.fex | 12345678 | 1234567890CARDTL | 1929216 | 73216 |
| cardscript.fex | 12345678 | 1234567890SCRIPT | 2002944 | 1894 |
| sunxi_gpt.fex | 12345678 | 1234567890___GPT | 2004992 | 8192 |
| sunxi_mbr_nor.fex | 12345678 | 1234567890___MBR | 2013184 | 16384 |
| dlinfo.fex | 12345678 | 1234567890DLINFO | 2029568 | 16384 |
| arisc.fex | 12345678 | 1234567890ARISC | 2045952 | 15 |
| melis_pkg_nor.fex | RFSFAT16 | MELIS_PKG_NOR_FE | 2046976 | 1589248 |
| Vmelis_pkg_nor.fex | RFSFAT16 | VMELIS_PKG_NOR_F | 3636224 | 4 |
| data_udisk.fex | RFSFAT16 | DATA_UDISK_FEX00 | 3637248 | 14614528 |
| Vdata_udisk.fex | RFSFAT16 | VDATA_UDISK_FEX0 | 18251776 | 4 |

Image size 18 252 800 bytes. Partitions are stored in table order, contiguously,
each starting on a 1024-byte boundary.

## Padding: two regions, not one

The plan's §2 described the padding as "the byte `0xCD`". Measured, there are two
distinct fill regions after every payload:

```
[offset,            offset+length)      payload
[offset+length,     offset+stored_len)  zero fill,  stored_len == align(length, 16)
[offset+stored_len, next 1024 boundary) 0xCD fill
```

Whole-image filler histogram over all 25 items:

```
{0x00: 70, 0xCD: 8128}
```

70 zero bytes and 8128 `0xCD` bytes. Filling both regions with `0xCD` does **not**
reproduce the image. Pinned by
`test_filler_is_zeroes_up_to_stored_len_then_cd_up_to_the_boundary` and
`test_whole_image_filler_histogram_is_seventy_zeroes_and_8128_cd`.

⚠️ UNVERIFIED: whether `0xCD` is a stable vendor convention or an artefact of the
build that produced this one image. Proving it needs a second, independently
built image from the same vendor to compare against.

## V-partitions and how the pairing is derived

Four of the 25 items form two pairs: a payload partition and a 4-byte partition
holding its checksum.

```
vsum(partition) = sum of the partition's little-endian u32 words, mod 2**32
```

Measured against the stock image:

| partition | V-partition | value |
|---|---|---|
| `data_udisk.fex` | `Vdata_udisk.fex` | `0x1e3c76a1` (`a1 76 3c 1e`) |
| `melis_pkg_nor.fex` | `Vmelis_pkg_nor.fex` | `0x814cb3db` (`db b3 4c 81`) |

The pairing is **not hardcoded.** `imagewty._v_pairs()` reads it out of the
`dlinfo.fex` partition at build time, so an image that pairs partitions
differently is handled without a code change:

```
records 2
bootA   start=32    size_sect=3200   sub=MELIS_PKG_NOR_FE  v=VMELIS_PKG_NOR_F
ROOTFS  start=3232  size_sect=28544  sub=DATA_UDISK_FEX00  v=VDATA_UDISK_FEX0
```

`dlinfo.fex` layout (`formats/imagewty.py` docstring): magic `0xfdce73ab` at
`0x00`, record count at `0x10`, then 72-byte records from `0x20`; each record has
`name[16]`, four u32 (`?`, `start_sector`, `?`, `size_sectors`), `subtype[16]`,
`vsubtype[16]`, two trailing u32.

Note that `dlinfo` independently corroborates the ROOTFS size: 28 544 sectors x
512 = **14 614 528** bytes, exactly `length` of `data_udisk.fex`. (The `bootA`
record's 3200 sectors = 1 638 400 bytes is the flash slot size, larger than
`melis_pkg_nor.fex`'s 1 589 248-byte payload — so `size_sectors` is a slot size,
not a payload length.)

`build()` recomputes a V-partition only when its paired partition appears in
`replace`. Nothing else in the image is touched:
`test_replacing_data_udisk_rewrites_exactly_that_byte_and_its_vsum` mutates one
byte of the ROOTFS and asserts the output differs from the vendor image in
exactly two places — that byte and the 4 bytes of `Vdata_udisk.fex`.

`vsum()` **raises `ValueError` on a length that is not a multiple of 4.** The plan
(§4 T07) called for ignoring a short tail. No stock partition has such a tail, so
silently ignoring one would only ever hide corruption. See `docs/findings.md`.

## Duplicate names: a name is not an address

`boot_pkg_uboot_nor.fex` appears **twice** in the table, under subtypes
`BOOTPKG-00000000` (offset 334 848) and `BOOTPKG-NOR00000` (offset 662 528). The
payloads are identical in this image, but they are two separate table entries at
two separate offsets.

Consequences, both pinned by tests:

* `build()` indexes payloads by **item position**, not by name — an earlier
  version keyed a dict by name and would have written the same replacement into
  both slots or dropped one.
* Passing that name in `replace` raises `ValueError` naming both subtypes rather
  than guessing. Guessing here means rewriting a bootloader the caller did not
  mean to touch.

`test_exactly_one_item_name_is_used_twice` also fails if a future image starts
duplicating a *different* name.

## Fixed-size guard

`data_udisk.fex` must stay 14 614 528 bytes. Its size is declared in two places
that live *outside* the IMAGEWTY container and that this builder does not
rewrite:

* `stock/partitions/sys_partition_nor.fex` — `[partition] name = ROOTFS, size = 28544` (sectors)
* `stock/rootfs/rootfs_ini.tmp` — `[IMAGE_CFG] size=14272` (KB)

28 544 x 512 = 14 272 x 1024 = 14 614 528. `build()` raises `ValueError` naming
both files if a replacement ROOTFS has any other length
(`test_resizing_data_udisk_raises_and_names_the_two_declarations`).

## The proof

`imagewty.build(img, {})` is byte-identical to the vendor `LTTF133.img`. So is
`build(img, {...})` when the replacements are the partitions' own bytes. That is
the claim the whole toolchain rests on: header, item table, both padding regions,
every unexplained field and every alignment come back out unchanged, so a
difference in the output can only exist where something was deliberately changed.

Run it:

```bash
./.venv/bin/python -m pytest -m stock tests/test_imagewty.py -q
```
