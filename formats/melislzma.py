"""melis-lzma - the chunked LZMA1 variant used for .mod / .drv / .plg / .axf.

EXPERIMENTAL AND LOSSY. Read the caveat before relying on this.

A stream is one or more chunks, each starting with the 5-byte LZMA1 properties
header (0x5d 0x00 0x80 0x00 0x00) and carrying no uncompressed-size field and no
end marker. Chunk boundaries are recovered by scanning for that signature, which
is a heuristic: the signature can occur inside compressed data, and the stock
init.axf round-trips to 2_501_594 bytes against a declared 2_501_564 - 30 bytes
too many. Good enough to read strings out of a binary, NOT good enough to
rebuild one.

None of this is on the theming path. Every apps/Data/*.data file is stored
uncompressed in MINFS, so a theme build never calls into this module. It exists
only for inspecting init.axf.

To make this correct you would need to find the chunk table that the loader
actually uses, rather than guessing boundaries from the signature.
"""
import lzma
import struct

PROPS = b'\x5d\x00\x80\x00\x00'


def _chunk_bounds(blob: bytes) -> list[int]:
    out, i = [], 0
    while True:
        i = blob.find(PROPS, i)
        if i < 0:
            break
        out.append(i)
        i += 1
    return out


def decompress(blob: bytes, size: int | None = None) -> bytes:
    """Best-effort decompression. May return slightly more bytes than declared."""
    bounds = _chunk_bounds(blob) or [0]
    bounds.append(len(blob))
    out = bytearray()
    for i in range(len(bounds) - 1):
        chunk = blob[bounds[i]:bounds[i + 1]]
        if len(chunk) <= 5:
            continue
        props = chunk[0]
        lc, rest = props % 9, props // 9
        lp, pb = rest % 5, rest // 5
        dict_size = struct.unpack_from('<I', chunk, 1)[0]
        filt = [{'id': lzma.FILTER_LZMA1, 'dict_size': max(dict_size, 1 << 16),
                 'lc': lc, 'lp': lp, 'pb': pb}]
        dec = lzma.LZMADecompressor(format=lzma.FORMAT_RAW, filters=filt)
        try:
            out += dec.decompress(chunk[5:])
        except lzma.LZMAError:
            pass
    return bytes(out[:size]) if size else bytes(out)


def compress(data: bytes) -> bytes:
    raise NotImplementedError(
        'melis-lzma compression is not implemented and is not needed for theming')
