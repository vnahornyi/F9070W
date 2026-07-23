# melis-lzma

The chunked LZMA1 variant Melis uses for `.mod`, `.drv`, `.plg` and `.axf` files
inside MINFS. Code: `formats/melislzma.py`. Tests: `tests/test_melislzma.py`.

## Read this first

**The decoder is approximate and there is no encoder. Firmware code cannot
currently be repacked.**

* `decompress()` returns *more* bytes than declared. On `/apps/init.axf` it
  produces **2 501 594** bytes against a declared **2 501 564** — 30 bytes too
  many.
* `compress()` exists only to raise `NotImplementedError`. It is not a stub
  waiting to be filled in with an off-the-shelf LZMA call; the container is not
  plain LZMA.
* Nothing on the theming path calls this module. All 75 `/apps/Data/*.data`
  screens are stored raw in MINFS, so a theme build never enters here.

What the module is good for: reading strings and structure out of `init.axf`.
`test_output_is_good_enough_to_read_strings_out_of_the_binary` asserts `CarPlay`
and `sourceSave` come out of it. What it is not good for: producing a binary you
would put on a device.

## What we know about the format

A stream is one or more chunks. Each chunk starts with the 5-byte LZMA1
properties header `5d 00 80 00 00`, and carries **no** uncompressed-size field
and **no** end marker — which is why a decoder has to know where each chunk
starts.

`decompress()` recovers the boundaries by scanning the blob for that 5-byte
signature. That is a heuristic and it is known to be wrong, because the signature
can occur inside compressed data and because a chunk can start without one.

On `init.axf` the scan gives `[0, 904944, 1075560]` — three chunks — and the
concatenated output overshoots by 30 bytes. Passing the declared size only
truncates the result; it does not make it correct, because the surplus is not
necessarily at the end.

## The lead: the chunk table is in the MINFS entry

This is the concrete next step, and it is not speculation about where to look —
the numbers are already sitting in the filesystem metadata.

The MINFS directory entry of every compressed file is **oversized**: its u32 at
`+0x10` has high bits set on top of the name length, and `entry_size` runs
188..348 bytes instead of `20 + align4(namelen)`. That happens for exactly the 69
compressed files and no others. The extra space is `(entry_size - 20 -
align4(namelen))` bytes, always a multiple of 32, giving 5, 6 or 10 records.

The first u32 of each 32-byte record is a byte offset into the compressed blob.
For 66 of the 69 files those offsets are exactly what the signature scan finds.
For the other three — `/mod/cedar/arec.plg`, `/mod/charset.mod`,
`/mod/slib.mod` — they differ, and those are precisely the files the scan gets
wrong:

| file | table offsets | signature scan |
|---|---|---|
| `/mod/cedar/arec.plg` | `0, 2648, 2976, 3112, 0, 3144` | `0, 2976` |
| `/mod/charset.mod` | `0, 32, 936, 120740, 120740, 120740` | `32, 936` |
| `/mod/slib.mod` | `0, 216, 6996, 7564, 7564, 7564` | `216` |

`/apps/init.axf`'s five records, as u32:

```
(      0,  904944, 1646244, 1646244, 3910139904, 1, 6, 2)
( 904944,  170613,  564028,  564028, 3911786148, 1, 2, 2)
(1075560,  101752,  290776,  290776, 3912350176, 1, 3, 2)
(      0,       0,       0,  186272, 3912640952, 8, 3, 0)
(1177312,      80,      80,      80, 4294901760, 1, 0, 1)
```

`1177312 + 80 = 1177392`, exactly the file's `stored_size`.

⚠️ UNVERIFIED: the meaning of every column after the first. Columns 2 and 3 look
like a compressed and an uncompressed chunk size, but `1646244 + 564028 + 290776
= 2 501 048`, which is not the declared 2 501 564, so that reading is wrong or
incomplete. Column 5 is large and increasing across records and may be a load
address. Proving any of it needs either the loader's reader disassembled out of
`init.axf`, or a second firmware image whose table can be diffed against this
one.

## What "fix this" means

1. Mask the `+0x10` field to its low 16 bits so `minfs` stops mis-reading it as a
   20 MB name length (that also removes the ~1.4 s cost of every
   `minfs.files()` call — see `docs/formats/minfs.md`).
2. Expose the 32-byte records as a parsed structure.
3. Drive `decompress()` from that table instead of the signature scan and check
   whether the +30 bytes on `init.axf` go away, and whether the three
   disagreeing files start decoding correctly.
4. Only then think about `compress()`: writing a stream means writing a matching
   table back into the MINFS entry, which means the entry layout has to be
   understood, not guessed.

Until step 3 lands, `tests/test_melislzma.py` pins the *current* inaccuracy to
the byte (2 501 594, +30) so that any change in behaviour is noticed rather than
assumed to be an improvement.
