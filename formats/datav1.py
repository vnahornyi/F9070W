"""DATAV1.0 - one UI screen: a layout section followed by a sprite section.

    0x00  "DATAV1.0" in UTF-16LE
    0x10  header size (0x20)
    0x14  layout size  -> sprite section starts here
    0x30  u32 width, 0x34 u32 height
    0x38  u32 window count
    0x64  window name, UTF-16LE, 208 bytes ("ViewShowWndWallPaper")
    ...   layout records: controls, geometry, colours   <- NOT decoded yet

    [sprite section]
      u32 count
      count x { u32 record_offset (absolute), u32 compressed_size }
      per sprite: 32-byte record header, then a zlib stream
        +0x00 u32 header size (32)
        +0x04 u32 width
        +0x08 u32 height
        +0x0c u32 flags
        +0x10 u32 format
        +0x14 u32 data offset (absolute)
        +0x18 ... preserved verbatim; meaning unknown but non-zero in 14 files

Pixels are BGRA8888 or RGB565 depending on the screen. Rather than trusting a
header field, the depth is derived from len(decompressed) / (w * h), which is
exact and has been verified across all 1128 sprites in the stock firmware.
"""
import io
import struct
import zlib
from dataclasses import dataclass

MAGIC = 'DATAV1.0'


def stride(width: int, depth: int) -> int:
    """Row pitch: width * depth rounded up to a 4-byte boundary."""
    return (width * depth + 3) // 4 * 4


@dataclass
class Sprite:
    idx: int
    offset: int
    width: int
    height: int
    header: bytes
    comp: bytes
    raw_len: int

    @property
    def depth(self) -> int:
        """Bytes per pixel: 4 = BGRA8888, 3 = BGR888, 2 = RGB565.

        Derived from the decompressed length rather than a header field, taking
        the 4-byte row padding into account. Verified against all 1128 stock
        sprites: 931 are BGR888, 132 BGRA8888, 65 RGB565.
        """
        for bpp in (4, 3, 2, 1):
            if stride(self.width, bpp) * self.height == self.raw_len:
                return bpp
        raise ValueError(
            f'sprite {self.idx}: cannot derive depth from {self.raw_len} bytes '
            f'for {self.width}x{self.height}')

    @property
    def stride(self) -> int:
        """Bytes per row, padded up to a 4-byte boundary."""
        return stride(self.width, self.depth)

    @property
    def mode(self) -> str:
        return {4: 'BGRA', 3: 'BGR', 2: 'RGB565'}[self.depth]

    def decode(self) -> bytes:
        """Raw buffer exactly as stored, row padding included."""
        return zlib.decompress(self.comp)

    def pixels(self) -> bytes:
        """Tightly packed pixels with the row padding stripped."""
        raw, row = self.decode(), self.width * self.depth
        if self.stride == row:
            return raw
        return b''.join(raw[y * self.stride:y * self.stride + row]
                        for y in range(self.height))

    def pack(self, pixels: bytes) -> bytes:
        """Inverse of pixels(): re-add row padding to a tightly packed buffer.

        The padding bytes are lifted from this sprite's own stored buffer, not
        synthesised, so pack(pixels()) reproduces decode() byte for byte. Their
        meaning is unknown, so a replaced sprite keeps the padding of the sprite
        it replaces rather than having it zeroed.
        """
        row = self.width * self.depth
        if len(pixels) != row * self.height:
            raise ValueError(f'sprite {self.idx}: expected {row * self.height} '
                             f'bytes of pixels, got {len(pixels)}')
        if self.stride == row:
            return pixels
        raw = self.decode()
        return b''.join(pixels[y * row:(y + 1) * row] +
                        raw[y * self.stride + row:(y + 1) * self.stride]
                        for y in range(self.height))


def _magic(d: bytes) -> str:
    return d[:16].decode('utf-16-le', 'replace')


def sprite_section(d: bytes) -> int:
    return struct.unpack_from('<I', d, 0x14)[0]


def screen_size(d: bytes) -> tuple[int, int]:
    return struct.unpack_from('<II', d, 0x30)


def window_name(d: bytes) -> str:
    return d[0x64:0x64 + 208].decode('utf-16-le', 'replace').split('\0')[0]


def sprites(d: bytes) -> list[Sprite]:
    if _magic(d) != MAGIC:
        raise ValueError(f'not a DATAV1.0 file (got {_magic(d)!r})')
    base = sprite_section(d)
    count = struct.unpack_from('<I', d, base)[0]
    out = []
    for i in range(count):
        off, csize = struct.unpack_from('<II', d, base + 4 + i * 8)
        hsize, w, h = struct.unpack_from('<III', d, off)
        doff = struct.unpack_from('<I', d, off + 0x14)[0]
        comp = d[doff:doff + csize]
        out.append(Sprite(i, off, w, h, d[off:off + hsize], comp,
                          len(zlib.decompress(comp))))
    return out


def rebuild(d: bytes, replace: dict[int, bytes] | None = None,
            level: int = 9) -> bytes:
    """Rebuild the sprite section, optionally swapping raw pixel buffers.

    `replace` maps sprite index -> raw pixels in that sprite's own mode and
    dimensions. The layout section is copied byte for byte, every record header
    is preserved except its data offset, so with replace={} the output is
    byte-identical to the input (see tools/verify.py).
    """
    replace = replace or {}
    base = sprite_section(d)
    items = sprites(d)
    body, index = io.BytesIO(), []
    cursor = base + 4 + len(items) * 8

    for sp in items:
        if sp.idx in replace:
            raw = replace[sp.idx]
            expect = sp.stride * sp.height
            if len(raw) != expect:
                raise ValueError(
                    f'sprite {sp.idx}: expected {expect} bytes '
                    f'({sp.width}x{sp.height} {sp.mode}, stride {sp.stride}), '
                    f'got {len(raw)} - pass Sprite.pack(pixels)')
            comp = zlib.compress(raw, level)
        else:
            comp = sp.comp
        rec = bytearray(sp.header)
        doff = cursor + len(rec)
        struct.pack_into('<I', rec, 0x14, doff)
        body.write(bytes(rec) + comp)
        index.append((cursor, len(comp)))
        cursor = doff + len(comp)

    out = bytearray(d[:base])
    out += struct.pack('<I', len(items))
    for off, size in index:
        out += struct.pack('<II', off, size)
    out += body.getvalue()
    return bytes(out)
