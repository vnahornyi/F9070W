# DATAV1.0

One UI screen: a layout section followed by a sprite section. 75 of them live in
`/apps/Data/*.data` inside the ROOTFS partition. Code: `formats/datav1.py`.
Tests: `tests/test_datav1.py`.

## File layout

```
0x00  "DATAV1.0" in UTF-16LE
0x10  u32 header size (0x20)
0x14  u32 layout size   -> the sprite section starts at this absolute offset
0x30  u32 width, 0x34 u32 height
0x38  u32 window count
0x64  window name, UTF-16LE, 208 bytes  (e.g. "ViewShowWndWallPaper")
...   layout records: controls, geometry, colours   <- NOT decoded
```

The layout section is **not decoded** and is copied byte for byte by `rebuild()`.
Decoding it is what a later session needs in order to move or remove a control
(see `docs/roadmap.md`).

Sprite section:

```
u32 count
count x { u32 record_offset (absolute), u32 compressed_size }
per sprite: a record header, then a raw zlib stream
```

Record header:

```
+0x00  u32 header size   (24 or 32 -- see below)
+0x04  u32 width
+0x08  u32 height
+0x0c  u32 flags
+0x10  u32 format
+0x14  u32 data offset (absolute)   -- the only field rebuild() rewrites
+0x18  8 bytes, present only in the 32-byte variant
```

## Sprites, depth and stride

Measured over all 75 stock screens: **1128 sprites, 31.6 Mpx**, of which 69
screens carry at least one sprite and 6 are pure layout.

Depth is **derived from the decompressed length**, not read from a header field:

```python
for bpp in (4, 3, 2, 1):
    if stride(width, bpp) * height == raw_len:
        return bpp
```

```
stride(w, depth) = align4(w * depth)
```

That derivation is exact for all 1128 sprites, and splits them:

| depth | mode | count |
|---|---|---:|
| 4 | BGRA8888 | 132 |
| 3 | BGR888 | 931 |
| 2 | RGB565 | 65 |

Depth-4 sprites never need row padding (`stride == w * 4`), which
`test_depth_four_sprites_are_bgra_and_need_no_row_padding` asserts on all 132.

`Sprite.pixels()` strips the row padding; `Sprite.pack()` puts it back;
`Sprite.decode()` is the buffer exactly as stored.

## Two record header sizes

The plan's §2 said "bytes `+0x18..0x20` are non-zero in 14 screens, purpose
unknown". Measured, the real distinction is the **header size**, and the tail
never varies:

```
header sizes {24: 788, 32: 340}
screens per header size {24: 55, 32: 14}, overlap 0
32-byte tails seen: {b'\x01\x00\x00\x00\x00\x00\x00\x00'}
```

* 788 sprites across 55 screens have a 24-byte header — there are no
  `+0x18..0x20` bytes at all.
* 340 sprites across 14 screens have a 32-byte header, whose `+0x18..0x20` is
  **always** `01 00 00 00 00 00 00 00`.
* No screen mixes the two.

Pinned by `test_stock_header_sizes_split_55_and_14_screens` and
`test_thirty_two_byte_headers_carry_a_constant_tail`.

⚠️ UNVERIFIED: what the 32-byte variant means. The tail is constant here, so this
image gives no signal at all about its semantics — a second firmware with a
different value would.

`rebuild()` copies each header verbatim except `+0x14`, whatever its size.

## The row-padding bug (fixed in `abd3cd3`)

`Sprite.pack()` used to *synthesise* the row padding as zero bytes. It looked
harmless — padding is padding. It was not.

Measured on the stock firmware: **543 of the 1128 sprites store non-zero row
padding, carrying 1020 distinct padding values.** Re-running the old behaviour as
a simulation over the stock tree:

```
zeroed padding: 21/69 screens survive, 543/1128 sprites corrupted
```

So a "change nothing" round-trip through PNG and back silently altered 48 of the
69 themeable screens.

The fix lifts the padding out of the sprite's own stored buffer:

```python
raw = self.decode()
return b''.join(pixels[y * row:(y + 1) * row] +
                raw[y * self.stride + row:(y + 1) * self.stride]
                for y in range(self.height))
```

so `pack(pixels()) == decode()` for every sprite, and a replaced sprite inherits
the padding of the sprite it replaces rather than having it zeroed. Pinned by
`test_no_stock_sprite_loses_its_row_padding` (1128 sprites, 0 lossy) and
`test_non_zero_row_padding_survives_a_rebuild`.

This is what made the end-to-end "stock PNGs through the whole chain change zero
bytes" test achievable at all.

⚠️ UNVERIFIED: what the non-zero padding bytes actually are. They may be nothing
but uninitialised memory from the vendor's own packer. That is precisely why they
are carried verbatim rather than normalised: an unexplained byte is not a byte
you get to decide is meaningless.

## Rebuild

`datav1.rebuild(d)` with no replacements is byte-identical to the input for all
75 stock screens and all six golden fixtures. `rebuild(d, {idx: raw})` requires
`len(raw) == stride * height` (i.e. the output of `Sprite.pack`) and raises
`ValueError` naming the expected size otherwise.

An untouched sprite keeps its stored zlib stream verbatim. A *replaced* one is
re-compressed with `zlib.compress(level=9)`, and that reproduces the vendor's own
stream byte for byte — proven the hard way by
`tests/test_build.py::test_stock_pngs_through_the_whole_chain_change_zero_bytes`,
which re-compresses all 1128 sprites from exported PNGs and still lands on the
original image.
