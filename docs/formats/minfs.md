# MINFS

The read-only filesystem Melis uses on the ROOTFS partition
(`data_udisk.fex`, 14 614 528 bytes). Code: `formats/minfs.py`. Tests:
`tests/test_minfs.py`.

## Layout

```
0x00  "MINFS"
0x08  u32 root_table_offset  (0x200)
0x0c  u32 root_table_size
0x10  u32 total entry count
0x14  u32 end of the metadata region
0x1c  u32 image size
```

Directory entry, variable length, 4-byte aligned:

```
0x00  u32 data_offset    file: absolute data offset; dir: child table offset
0x04  u32 stored_size    file: bytes on disk;        dir: child table size
0x08  u32 original_size  file: uncompressed size;    dir: 0
0x0c  u16 entry_size     total bytes of this entry
0x0e  u16 attr           1 = directory, 0 = file
0x10  u32 see below      low 16 bits are the name length
0x14  name, NUL-padded to a multiple of 4
```

A directory table is a run of entries; `walk()` recurses into any entry with
`attr == 1`.

## Compression is signalled by size equality

```
stored_size == original_size  ->  stored raw
stored_size != original_size  ->  melis-lzma (see melis-lzma.md)
```

There is no compression flag; `Node.compressed` is exactly that comparison.

Measured on the stock partition (`formats.minfs.files`):

* **257 files**
* **188 stored raw**
* **69 melis-lzma compressed** — the `.mod` / `.drv` / `.plg` / `.axf` files,
  which is precisely the extension list in `stock/rootfs/rootfs_ini.tmp`
  (`compress0=drv, compress1=mod, compress2=plg, compress3=axf`)
* all **75** `/apps/Data/*.data` screens are stored raw, so the theming path never
  touches the LZMA code

## The free tail

```
free_offset = align16(max(offset + stored) over all files) = 11_950_720
tail        = 14_614_528 - 11_950_720 = 2_663_808 bytes
```

`free_offset` is **not monotonic** — the plan called it that. It is
`max(offset + stored)`, so shrinking whichever file currently sits highest lowers
it again (`test_free_offset_grows_with_the_relocated_block_but_is_not_monotonic`).

## Relocation

`minfs.replace(partition, path, blob)` always stores the new blob raw:

* if `len(blob) <= node.stored`, it is written **in place** at the original offset;
* otherwise it is written at `free_offset(d)` and the entry is repointed;
* if it will not fit in the tail, `ValueError('no room: ...')`.

Only the target entry's first 12 bytes (`data_offset`, `stored_size`,
`original_size`) are rewritten. The header, every directory table, every other
entry and every other file's bytes are left exactly as they were —
`test_patch_keeps_257_files_and_moves_no_other_entry` and
`test_patch_touches_only_the_target_entry_in_the_metadata_region` are the
regression that would otherwise silently truncate a neighbouring file. The
partition never changes length.

Because the replacement is stored raw with `stored == original`, `replace()` also
works on a file that *was* compressed — which matters because we cannot produce a
valid melis-lzma stream.

⚠️ UNVERIFIED: whether the loader actually accepts a formerly-compressed file
stored raw. `init.axf` would fit raw with ~1.3 MB of tail to spare, but nothing
here proves the loader tolerates it. Proving it needs a device with a confirmed
recovery path — see `docs/hardware.md`, which currently says there is none.

## Finding: the `+0x10` u32 is not just a name length

`_read_entry` treats the u32 at entry `+0x10` as the name length. For the 188 raw
files it is exactly that. For **all 69 compressed files** its high half is set:

* `nlen & 0xffff` is the real name length in all 257 entries;
* `nlen > 0x100` in exactly 69 entries — exactly the compressed ones;
* their `entry_size` runs 188..348 bytes instead of `20 + align4(namelen)`.

The extra bytes are a **chunk table**. Measured across all 69:
`(entry_size - 20 - align4(namelen))` is a multiple of 32 in every case, giving 5,
6 or 10 records of 32 bytes each. The first u32 of each record is a byte offset
into the compressed blob. For **66 of the 69** files those leading offsets are
exactly the boundaries `melislzma._chunk_bounds` rediscovers by scanning for the
`5d 00 80 00 00` signature; the 3 that disagree
(`/mod/cedar/arec.plg`, `/mod/charset.mod`, `/mod/slib.mod`) are precisely the
files where the signature scan is wrong.

`/apps/init.axf`'s five records, as u32:

```
(      0,  904944, 1646244, 1646244, 3910139904, 1, 6, 2)
( 904944,  170613,  564028,  564028, 3911786148, 1, 2, 2)
(1075560,  101752,  290776,  290776, 3912350176, 1, 3, 2)
(      0,       0,       0,  186272, 3912640952, 8, 3, 0)
(1177312,      80,      80,      80, 4294901760, 1, 0, 1)
```

`0, 904944, 1075560` are the chunk boundaries the heuristic guesses. `1177312 + 80
== 1177392 ==` the file's `stored_size`.

⚠️ UNVERIFIED: the meaning of the individual fields, including the second and
third columns (which look like compressed and uncompressed chunk sizes but do not
sum to the declared 2 501 564), the large fourth column, and the trailing three.
Proving it needs decoding the loader's reader in `init.axf`, or a second firmware
image to diff the table against.

This is the concrete next step for `melis-lzma` — see `docs/roadmap.md`.

## Known defect: `_read_entry` is accidentally quadratic

Because it takes the whole u32 at `+0x10` as a name length, `_read_entry` slices
up to `0x0140_0000` (20 MB) out of the partition before `split(b'\0')` cuts it
back to 8 characters. Parsing is *correct* — the name comes out right — but one
`minfs.files()` call on the stock partition costs **1.38 s** measured, and
`replace()` calls `files()` twice. That is why the stock test suite runs for
minutes.

Masking the field to its low 16 bits fixes both the layout understanding and the
performance. Not done here because this segment changes no code.
